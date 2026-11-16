import hashlib
import json

import httpx
import pytest
from rest_framework.test import APIClient

from agent.client import AgentClient
from agent.config import Config
from agent.runner import Runner
from backend.tasks.domain.enums import TaskStatus
from backend.tasks.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db(transaction=True)


def test_real_backend_claim_collect_and_result_with_lost_acknowledgment() -> None:
    Device.objects.create(id="pc-42", token_digest=hashlib.sha256(b"device-secret").hexdigest())
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    api = APIClient()
    submissions: list[bytes] = []
    completed_at: list[object] = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        response = api.post(
            request.url.path,
            data=request.content,
            content_type="application/json",
            HTTP_AUTHORIZATION=request.headers["Authorization"],
        )
        if request.url.path.endswith("/result/"):
            submissions.append(request.content)
            task.refresh_from_db()
            completed_at.append(task.completed_at)
            assert response.status_code == 200
            if len(submissions) == 1:
                raise httpx.ReadTimeout("ack lost", request=request)
        return httpx.Response(response.status_code, content=response.content)

    with httpx.Client(transport=httpx.MockTransport(dispatch)) as http:
        runner = Runner(AgentClient(Config("http://testserver", "pc-42", "device-secret"), http))
        assert runner.step() is False
        task.refresh_from_db()
        assert task.status == TaskStatus.COMPLETED
        assert runner.step() is True
        assert runner.pending is None
    assert len(submissions) == 2
    assert submissions[0] == submissions[1]
    assert completed_at[0] == completed_at[1]
    payload = json.loads(submissions[0])
    assert set(payload["result"]) == {"os", "os_version", "cpu_count", "ram_gb"}
    task.refresh_from_db()
    assert task.result == payload["result"]
    assert task.attempt == 1
