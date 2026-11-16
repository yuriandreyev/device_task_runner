import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from backend.tasks.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def device_client() -> APIClient:
    Device.objects.create(
        id="pc-42", name="Demo", token_digest=hashlib.sha256(b"device-secret").hexdigest()
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer device-secret")
    return client


def test_claim_commits_attempt_and_blocks_second_claim(device_client: APIClient) -> None:
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    before = timezone.now()
    response = device_client.post("/api/agents/pc-42/claim/")
    after = timezone.now()
    assert response.status_code == 200
    data = response.json()
    task.refresh_from_db()
    assert task.status == "running"
    assert task.attempt == 1
    assert task.claim_token and len(task.claim_token) >= 43
    assert task.lease_until is not None
    assert before + timedelta(seconds=60) <= task.lease_until <= after + timedelta(seconds=60)
    assert data == {
        "id": task.pk,
        "action": "collect_system_info",
        "attempt": 1,
        "claim_token": task.claim_token,
        "lease_until": data["lease_until"],
    }
    assert parse_datetime(data["lease_until"]) == task.lease_until
    empty = device_client.post("/api/agents/pc-42/claim/")
    assert empty.status_code == 204
    assert empty.content == b""


def test_expired_attempt_is_reissued_with_new_credentials(device_client: APIClient) -> None:
    task = Task.objects.create(
        device_id="pc-42",
        action="collect_system_info",
        status="running",
        attempt=1,
        claim_token="old-token",
        lease_until=timezone.now() - timedelta(seconds=1),
    )
    response = device_client.post("/api/agents/pc-42/claim/")
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.attempt == 2
    assert task.claim_token != "old-token"
    assert task.claim_token == response.json()["claim_token"]
    assert task.lease_until is not None and task.lease_until > timezone.now()
    assert task.status == "running"


def test_empty_queue_does_not_include_other_devices_or_terminal_tasks(
    device_client: APIClient,
) -> None:
    Device.objects.create(id="other", name="Other", token_digest="a" * 64)
    other_task = Task.objects.create(device_id="other", action="collect_system_info")
    Task.objects.create(device_id="pc-42", action="collect_system_info", status="completed")
    Task.objects.create(device_id="pc-42", action="collect_system_info", status="failed")
    assert device_client.post("/api/agents/pc-42/claim/").status_code == 204
    other_task.refresh_from_db()
    assert other_task.status == "pending"
    assert other_task.attempt == 0


def test_claim_selects_oldest_eligible_task(device_client: APIClient) -> None:
    older = Task.objects.create(device_id="pc-42", action="collect_system_info")
    newer = Task.objects.create(device_id="pc-42", action="collect_system_info")
    assert device_client.post("/api/agents/pc-42/claim/").json()["id"] == older.pk
    assert device_client.post("/api/agents/pc-42/claim/").json()["id"] == newer.pk


def test_device_cannot_claim_for_another_device(device_client: APIClient) -> None:
    Device.objects.create(id="other", name="Other", token_digest="a" * 64)
    task = Task.objects.create(device_id="other", action="collect_system_info")
    assert device_client.post("/api/agents/other/claim/").status_code == 403
    task.refresh_from_db()
    assert task.attempt == 0
    assert task.status == "pending"


@pytest.mark.parametrize("credential", ["", "Bearer invalid", "Token device-secret"])
def test_claim_rejects_invalid_credentials(device_client: APIClient, credential: str) -> None:
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    device_client.credentials(HTTP_AUTHORIZATION=credential)
    assert device_client.post("/api/agents/pc-42/claim/").status_code == 401
    task.refresh_from_db()
    assert task.attempt == 0


def test_administrator_token_cannot_claim(admin_client: APIClient) -> None:
    assert admin_client.post("/api/agents/pc-42/claim/").status_code == 401


def test_concurrent_claims_return_exactly_one_attempt(device_client: APIClient) -> None:
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    barrier = Barrier(2)

    def claim() -> tuple[int, dict[str, object] | None]:
        try:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer device-secret")
            barrier.wait(timeout=5)
            response = client.post("/api/agents/pc-42/claim/")
            return response.status_code, response.json() if response.status_code == 200 else None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim), pool.submit(claim)]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(status for status, _ in results) == [200, 204]
    task.refresh_from_db()
    assert task.attempt == 1
    assert task.status == "running"
    successful = [payload for status, payload in results if status == 200]
    assert successful[0] is not None
    assert successful[0]["id"] == task.pk
    assert successful[0]["claim_token"] == task.claim_token
