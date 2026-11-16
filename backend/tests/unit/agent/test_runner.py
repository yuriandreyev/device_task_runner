import json
import logging
from unittest.mock import Mock

import httpx
import pytest

from agent.client import AgentClient, AgentError, Claim, PendingResult
from agent.config import Config
from agent.runner import Runner

CONFIG = Config("https://example.test", "pc-42", "device-secret")
CLAIM = {"id": 73, "action": "collect_system_info", "claim_token": "claim-secret"}


@pytest.mark.parametrize("failure", ["timeout", "server-error"])
def test_delivery_retry_uses_identical_bytes_without_collecting_or_claiming_again(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    requests: list[httpx.Request] = []
    collect = Mock(return_value={"os": "Linux"})

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer device-secret"
        assert request.extensions["timeout"] == {
            "connect": 5.0,
            "read": 10.0,
            "write": 10.0,
            "pool": 10.0,
        }
        if len(requests) == 1:
            return httpx.Response(200, json=CLAIM)
        if len(requests) == 2:
            if failure == "timeout":
                raise httpx.ReadTimeout("device-secret claim-secret", request=request)
            return httpx.Response(503, text="device-secret claim-secret")
        return httpx.Response(200)

    sleep = Mock()
    jitter = Mock(return_value=25.0)
    with (
        caplog.at_level(logging.INFO),
        httpx.Client(transport=httpx.MockTransport(respond)) as http,
    ):
        runner = Runner(AgentClient(CONFIG, http), collect=collect, sleep=sleep, jitter=jitter)
        assert runner.run(once=True) == 0
        assert runner.pending is None
    assert [r.url.path for r in requests] == [
        "/api/agents/pc-42/claim/",
        "/api/tasks/73/result/",
        "/api/tasks/73/result/",
    ]
    assert requests[1].content == requests[2].content
    assert json.loads(requests[2].content) == {
        "claim_token": "claim-secret",
        "status": "completed",
        "result": {"os": "Linux"},
    }
    collect.assert_called_once_with()
    sleep.assert_called_once_with(25.0)
    jitter.assert_called_once_with(24.0, 36.0)
    assert "device-secret" not in caplog.text
    assert "claim-secret" not in caplog.text


@pytest.mark.parametrize("action", ["collect_system_info", "rm -rf /", "shell"])
def test_action_failure_and_unknown_actions_send_failed_without_secrets(
    action: str, caplog: pytest.LogCaptureFixture
) -> None:
    collect = Mock(side_effect=OSError("device-secret claim-secret"))
    submissions: list[bytes] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/claim/"):
            return httpx.Response(200, json={**CLAIM, "action": action})
        submissions.append(request.content)
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert Runner(AgentClient(CONFIG, http), collect=collect).run(once=True) == 0
    payload = json.loads(submissions[0])
    assert payload["status"] == "failed"
    assert "result" not in payload
    assert payload["error"] == (
        "System information collection failed (OSError)"
        if action == "collect_system_info"
        else "Unsupported action"
    )
    assert collect.call_count == (1 if action == "collect_system_info" else 0)
    assert "secret" not in caplog.text


def test_failed_result_is_also_retried_without_reexecution() -> None:
    submissions: list[bytes] = []
    collect = Mock(side_effect=RuntimeError("private"))

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/claim/"):
            return httpx.Response(200, json=CLAIM)
        submissions.append(request.content)
        return httpx.Response(502 if len(submissions) == 1 else 200)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert Runner(AgentClient(CONFIG, http), collect=collect, sleep=Mock()).run(once=True) == 0
    assert len(submissions) == 2
    assert submissions[0] == submissions[1]
    collect.assert_called_once_with()


def test_continuous_mode_recovers_claim_network_failure_and_conflict_then_polls_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[str] = []
    collect = Mock(return_value={})

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if len(requests) == 1:
            raise httpx.ConnectError("device-secret", request=request)
        if len(requests) == 2:
            return httpx.Response(200, json=CLAIM)
        if len(requests) == 3:
            return httpx.Response(409, text="claim-secret")
        return httpx.Response(204)

    sleep = Mock(side_effect=[None, None, KeyboardInterrupt])
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        runner = Runner(AgentClient(CONFIG, http), collect=collect, sleep=sleep)
        with pytest.raises(KeyboardInterrupt):
            runner.run()
        assert runner.pending is None
    assert requests == [
        "/api/agents/pc-42/claim/",
        "/api/agents/pc-42/claim/",
        "/api/tasks/73/result/",
        "/api/agents/pc-42/claim/",
    ]
    assert all(24 <= call.args[0] <= 36 for call in sleep.call_args_list)
    assert "conflict" in caplog.text
    assert "secret" not in caplog.text


def test_once_empty_queue_and_exhausted_retries() -> None:
    collect = Mock()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(204))) as http:
        assert Runner(AgentClient(CONFIG, http), collect=collect).run(once=True) == 0
    collect.assert_not_called()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
        sleep = Mock()
        assert Runner(AgentClient(CONFIG, http), sleep=sleep).run(once=True) == 1
        assert sleep.call_count == 2


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404])
def test_permanent_http_errors_stop_without_exposing_response(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="secret"))
    ) as http:
        assert Runner(AgentClient(CONFIG, http)).run(once=True) == 1
    assert f"HTTP {status}" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.parametrize(
    "body", [None, [], {}, {**CLAIM, "id": True}, {**CLAIM, "claim_token": ""}]
)
def test_malformed_claim_is_rejected_before_action(body: object) -> None:
    collect = Mock()
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ) as http:
        assert Runner(AgentClient(CONFIG, http), collect=collect).run(once=True) == 1
    collect.assert_not_called()


def test_credentials_and_result_not_in_object_reprs() -> None:
    claim = Claim(73, "collect_system_info", "claim-secret")
    result = PendingResult.completed(claim, {"os": "private"})
    assert "secret" not in repr(claim)
    assert "private" not in repr(result)
    assert "secret" not in repr(result)


def test_result_permanent_error_retains_pending_without_reexecution() -> None:
    count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(200, json=CLAIM) if count == 1 else httpx.Response(400)

    collect = Mock(return_value={})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        runner = Runner(AgentClient(CONFIG, http), collect=collect)
        assert runner.run(once=True) == 1
        assert runner.pending is not None
        with pytest.raises(AgentError):
            runner.step()
    collect.assert_called_once_with()
