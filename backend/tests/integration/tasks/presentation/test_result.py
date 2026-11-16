import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import connections
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from backend.tasks.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def client() -> APIClient:
    Device.objects.create(id="pc-42", token_digest=hashlib.sha256(b"secret").hexdigest())
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer secret")
    return client


@pytest.fixture
def task(client: APIClient) -> Task:
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    assert client.post("/api/agents/pc-42/claim/").status_code == 200
    task.refresh_from_db()
    return task


def submit(client: APIClient, task: Task, **payload: object) -> Response:
    return client.post(
        f"/api/tasks/{task.pk}/result/",
        {
            "claim_token": task.claim_token,
            "status": "completed",
            "result": {"os": "Linux"},
            **payload,
        },
        format="json",
    )


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_result_is_terminal_and_retry_does_not_change_any_fields(
    client: APIClient, task: Task, terminal: str
) -> None:
    payload: dict[str, object] = {"claim_token": task.claim_token, "status": terminal}
    if terminal == "completed":
        payload["result"] = {"os": "Linux"}
    else:
        payload["error"] = "failure"
    url = f"/api/tasks/{task.pk}/result/"
    assert client.post(url, payload, format="json").status_code == 200
    task.refresh_from_db()
    assert task.status == terminal
    assert task.completed_at is not None
    assert task.result == ({"os": "Linux"} if terminal == "completed" else None)
    assert task.error == ("failure" if terminal == "failed" else "")
    snapshot = Task.objects.values().get(pk=task.pk)
    assert client.post(url, payload, format="json").status_code == 200
    assert Task.objects.values().get(pk=task.pk) == snapshot
    assert client.post("/api/agents/pc-42/claim/").status_code == 204


def test_conflicting_retry_and_wrong_token_leave_result_unchanged(
    client: APIClient, task: Task
) -> None:
    assert submit(client, task).status_code == 200
    snapshot = Task.objects.values().get(pk=task.pk)
    assert submit(client, task, result={"os": "Other"}).status_code == 409
    assert submit(client, task, claim_token="wrong").status_code == 409
    assert submit(client, task, claim_token="токен").status_code == 409
    assert Task.objects.values().get(pk=task.pk) == snapshot


def test_expired_lease_accepts_current_token(client: APIClient, task: Task) -> None:
    Task.objects.filter(pk=task.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    assert submit(client, task).status_code == 200


def test_reclaim_rejects_old_token(client: APIClient, task: Task) -> None:
    Task.objects.filter(pk=task.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    assert client.post("/api/agents/pc-42/claim/").status_code == 200
    assert submit(client, task).status_code == 409
    task.refresh_from_db()
    assert task.status == "running"
    assert task.attempt == 2
    assert submit(client, task).status_code == 200


def test_other_device_pending_and_missing_task(client: APIClient, task: Task) -> None:
    Device.objects.create(id="other", token_digest="a" * 64)
    Task.objects.filter(pk=task.pk).update(device_id="other")
    assert submit(client, task).status_code == 403
    task.refresh_from_db()
    assert task.status == "running"
    pending = Task.objects.create(device_id="pc-42", action="collect_system_info")
    assert submit(client, pending, claim_token="token").status_code == 409
    assert (
        client.post(
            "/api/tasks/999999/result/",
            {"claim_token": "token", "status": "completed", "result": {}},
            format="json",
        ).status_code
        == 404
    )


@pytest.mark.parametrize("credential", ["", "Bearer invalid", "Token secret"])
def test_authentication(client: APIClient, task: Task, credential: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=credential)
    assert submit(client, task).status_code == 401


def test_administrator_cannot_submit(admin_client: APIClient, task: Task) -> None:
    assert submit(admin_client, task).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"claim_token": "x", "status": "running"},
        {"claim_token": "x", "status": "completed"},
        {"claim_token": "x", "status": "completed", "result": []},
        {"claim_token": "x", "status": "completed", "result": None},
        {"claim_token": "x", "status": "completed", "result": {}, "error": "oops"},
        {"claim_token": "x", "status": "failed"},
        {"claim_token": "x", "status": "failed", "error": ""},
        {"claim_token": "x", "status": "failed", "error": "oops", "result": {}},
        {"claim_token": "", "status": "completed", "result": {}},
        {"claim_token": "x", "status": "completed", "result": {}, "extra": 1},
    ],
)
def test_invalid_payload_does_not_mutate_task(
    client: APIClient, task: Task, payload: dict[str, object]
) -> None:
    snapshot = Task.objects.values().get(pk=task.pk)
    response = client.post(f"/api/tasks/{task.pk}/result/", payload, format="json")
    assert response.status_code == 400
    assert Task.objects.values().get(pk=task.pk) == snapshot


@pytest.mark.parametrize("identical", [True, False])
def test_simultaneous_results_are_serialized(
    client: APIClient, task: Task, identical: bool
) -> None:
    assert connections["default"].vendor == "postgresql"
    barrier = Barrier(2)

    def finish(value: str) -> int:
        try:
            worker = APIClient()
            worker.credentials(HTTP_AUTHORIZATION="Bearer secret")
            barrier.wait(timeout=5)
            return submit(worker, task, result={"os": value}).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(finish, "Linux"),
            pool.submit(finish, "Linux" if identical else "Other"),
        ]
        statuses = sorted(f.result(timeout=10) for f in futures)
    assert statuses == ([200, 200] if identical else [200, 409])
    task.refresh_from_db()
    assert task.status == "completed"
    assert task.result in [{"os": "Linux"}, {"os": "Other"}]
