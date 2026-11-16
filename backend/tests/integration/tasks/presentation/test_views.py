import hashlib

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from backend.tasks.domain.enums import TaskStatus
from backend.tasks.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db


def test_create_and_read_task(admin_client: APIClient) -> None:
    Device.objects.create(id="pc-42", name="Demo", token_digest="a" * 64)
    response = admin_client.post(
        "/api/tasks/", {"device_id": "pc-42", "action": "collect_system_info"}, format="json"
    )
    assert response.status_code == 201
    data = response.json()
    task = Task.objects.get(pk=data["id"])
    assert (task.device_id, task.action, task.status, task.attempt) == (
        "pc-42",
        "collect_system_info",
        TaskStatus.PENDING,
        0,
    )
    task.claim_token = "secret-attempt"
    task.result = {"os": "Linux"}
    task.error = ""
    task.status = TaskStatus.COMPLETED
    task.attempt = 1
    task.save()
    response = admin_client.get(f"/api/tasks/{task.pk}/")
    assert response.status_code == 200
    assert response.json() == {
        "id": task.pk,
        "device_id": "pc-42",
        "action": "collect_system_info",
        "status": TaskStatus.COMPLETED,
        "attempt": 1,
        "result": {"os": "Linux"},
        "error": "",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"device_id": "pc-42", "action": "shell"},
        {"device_id": "pc-42"},
        {"action": "collect_system_info"},
        {"device_id": "bad/id", "action": "collect_system_info"},
    ],
)
def test_invalid_task_is_not_created(admin_client: APIClient, payload: dict[str, str]) -> None:
    assert admin_client.post("/api/tasks/", payload, format="json").status_code == 400
    assert not Task.objects.exists()


def test_missing_device_and_task_return_404(admin_client: APIClient) -> None:
    response = admin_client.post(
        "/api/tasks/", {"device_id": "missing", "action": "collect_system_info"}, format="json"
    )
    assert response.status_code == 404
    assert not Task.objects.exists()
    assert admin_client.get("/api/tasks/999999/").status_code == 404


@pytest.mark.parametrize("authorization", ["", "Token invalid", "Token", "Bearer invalid"])
def test_invalid_credentials_cannot_create_or_read_tasks(authorization: str) -> None:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=authorization)
    assert client.post("/api/tasks/", {}, format="json").status_code == 401
    assert client.get("/api/tasks/1/").status_code == 401
    assert not Task.objects.exists()


def test_create_requires_custom_permission() -> None:
    user = User.objects.create_user(username="reader", is_staff=True)
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    Device.objects.create(id="pc-42", name="Demo", token_digest="a" * 64)
    response = client.post(
        "/api/tasks/", {"device_id": "pc-42", "action": "collect_system_info"}, format="json"
    )
    assert response.status_code == 403
    assert not Task.objects.exists()
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    assert client.get(f"/api/tasks/{task.pk}/").status_code == 200


def test_inactive_user_token_is_rejected() -> None:
    user = User.objects.create_user(username="inactive", is_active=False)
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert client.get("/api/tasks/1/").status_code == 401


@pytest.mark.parametrize("scheme", ["Token", "Bearer"])
def test_device_token_cannot_access_administrative_api(scheme: str) -> None:
    device_token = "test-device-token"
    Device.objects.create(
        id="pc-42", name="Demo", token_digest=hashlib.sha256(device_token.encode()).hexdigest()
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"{scheme} {device_token}")
    assert client.post("/api/tasks/", {}, format="json").status_code == 401
    assert client.get("/api/tasks/1/").status_code == 401


def test_session_login_does_not_bypass_token_authentication() -> None:
    user = User.objects.create_superuser(username="root", password="test-password")
    client = APIClient()
    client.force_login(user)
    assert client.get("/api/tasks/1/").status_code == 401
