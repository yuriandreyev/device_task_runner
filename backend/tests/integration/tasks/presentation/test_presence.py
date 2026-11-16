import hashlib
from unittest.mock import Mock

import pytest
from redis import Redis
from redis.exceptions import ConnectionError, TimeoutError
from rest_framework.test import APIClient

from backend.config.urls import presence
from backend.tasks.domain.enums import TaskStatus
from backend.tasks.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def redis_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock(spec=Redis)
    client.exists.return_value = 0
    monkeypatch.setattr(presence, "client", client)
    return client


@pytest.fixture
def device_client() -> APIClient:
    Device.objects.create(id="pc-42", token_digest=hashlib.sha256(b"secret").hexdigest())
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    return client


@pytest.mark.parametrize(("exists", "status"), [(1, "online"), (0, "offline")])
def test_authenticated_presence_read(
    admin_client: APIClient, device_client: APIClient, redis_client: Mock, exists: int, status: str
) -> None:
    redis_client.exists.return_value = exists
    response = admin_client.get("/api/devices/pc-42/presence/")
    assert response.status_code == 200
    assert response.json() == {"device_id": "pc-42", "status": status}
    redis_client.exists.assert_called_once_with("agent:pc-42:online")
    redis_client.set.assert_not_called()


def test_missing_device_does_not_read_redis(admin_client: APIClient, redis_client: Mock) -> None:
    assert admin_client.get("/api/devices/missing/presence/").status_code == 404
    redis_client.exists.assert_not_called()


def test_device_token_and_anonymous_cannot_read_presence(
    device_client: APIClient, redis_client: Mock
) -> None:
    assert device_client.get("/api/devices/pc-42/presence/").status_code == 401
    device_client.credentials()
    assert device_client.get("/api/devices/pc-42/presence/").status_code == 401
    redis_client.exists.assert_not_called()


def test_disabled_presence_is_unknown_but_tasks_continue(
    admin_client: APIClient, device_client: APIClient
) -> None:
    assert admin_client.get("/api/devices/pc-42/presence/").json()["status"] == "unknown"
    assert device_client.post("/api/agents/pc-42/claim/").status_code == 204


def test_claim_and_result_refresh_only_the_marker_with_90_second_ttl(
    device_client: APIClient, redis_client: Mock
) -> None:
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    claim = device_client.post("/api/agents/pc-42/claim/")
    assert claim.status_code == 200
    assert device_client.post("/api/agents/pc-42/claim/").status_code == 204
    payload = {
        "claim_token": claim.json()["claim_token"],
        "status": TaskStatus.COMPLETED,
        "result": {"os": "Linux"},
    }
    url = f"/api/tasks/{task.pk}/result/"
    assert device_client.post(url, payload, format="json").status_code == 200
    assert device_client.post(url, payload, format="json").status_code == 200
    payload["result"] = {"os": "Other"}
    assert device_client.post(url, payload, format="json").status_code == 409
    assert redis_client.set.call_count == 5
    assert all(
        call.args == ("agent:pc-42:online", "1") and call.kwargs == {"ex": 90}
        for call in redis_client.set.call_args_list
    )


@pytest.mark.parametrize("error", [ConnectionError, TimeoutError])
def test_redis_failure_preserves_claim_result_and_retry_semantics(
    admin_client: APIClient,
    device_client: APIClient,
    redis_client: Mock,
    error: type[Exception],
    caplog: pytest.LogCaptureFixture,
) -> None:
    redis_client.set.side_effect = error("redis://secret@example.test/0")
    redis_client.exists.side_effect = error("redis://secret@example.test/0")
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    claim = device_client.post("/api/agents/pc-42/claim/")
    assert claim.status_code == 200
    assert device_client.post("/api/agents/pc-42/claim/").status_code == 204
    payload = {
        "claim_token": claim.json()["claim_token"],
        "status": TaskStatus.COMPLETED,
        "result": {"os": "Linux"},
    }
    url = f"/api/tasks/{task.pk}/result/"
    assert device_client.post(url, payload, format="json").status_code == 200
    snapshot = Task.objects.values().get(pk=task.pk)
    assert device_client.post(url, payload, format="json").status_code == 200
    assert Task.objects.values().get(pk=task.pk) == snapshot
    task.refresh_from_db()
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"os": "Linux"}
    assert admin_client.get("/api/devices/pc-42/presence/").json()["status"] == "unknown"
    assert "secret" not in caplog.text


def test_rejected_requests_do_not_refresh_another_devices_presence(
    device_client: APIClient, redis_client: Mock
) -> None:
    Device.objects.create(id="other", token_digest="a" * 64)
    task = Task.objects.create(device_id="other", action="collect_system_info")
    assert device_client.post("/api/agents/other/claim/").status_code == 403
    assert (
        device_client.post(
            f"/api/tasks/{task.pk}/result/",
            {"claim_token": "wrong", "status": TaskStatus.COMPLETED, "result": {}},
            format="json",
        ).status_code
        == 403
    )
    assert (
        device_client.post(
            "/api/tasks/999999/result/",
            {"claim_token": "wrong", "status": TaskStatus.COMPLETED, "result": {}},
            format="json",
        ).status_code
        == 404
    )
    assert device_client.post(f"/api/tasks/{task.pk}/result/", {}, format="json").status_code == 400
    device_client.credentials()
    assert device_client.post("/api/agents/pc-42/claim/").status_code == 401
    redis_client.set.assert_not_called()


def test_real_connection_refusal_does_not_prevent_claim_or_result(
    admin_client: APIClient, device_client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    from backend.tasks.infrastructure.presence import RedisPresence

    # A bound, non-listening socket refuses connections without stopping any service.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        adapter = RedisPresence.from_url(f"redis://127.0.0.1:{unavailable.getsockname()[1]}/0")
        monkeypatch.setattr(presence, "client", adapter.client)
        try:
            task = Task.objects.create(device_id="pc-42", action="collect_system_info")
            claim = device_client.post("/api/agents/pc-42/claim/")
            assert claim.status_code == 200
            response = device_client.post(
                f"/api/tasks/{task.pk}/result/",
                {
                    "claim_token": claim.json()["claim_token"],
                    "status": TaskStatus.FAILED,
                    "error": "collection failed",
                },
                format="json",
            )
            assert response.status_code == 200
            task.refresh_from_db()
            assert task.status == TaskStatus.FAILED
            assert task.error == "collection failed"
            assert admin_client.get("/api/devices/pc-42/presence/").json()["status"] == "unknown"
        finally:
            assert adapter.client is not None
            adapter.client.close()
