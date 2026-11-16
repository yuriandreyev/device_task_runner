import hashlib
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from devices.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db


def test_create_demo_device_stores_only_digest_and_preserves_existing_token() -> None:
    output = StringIO()
    call_command("create_demo_device", "pc-42", stdout=output)
    lines = dict(line.split("=", 1) for line in output.getvalue().splitlines())
    assert lines["device_id"] == "pc-42"
    token = lines["device_token"]
    assert len(token) >= 43
    device = Device.objects.get(pk="pc-42")
    assert device.name == "pc-42"
    assert device.token_digest == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(Device.objects.filter(pk=device.pk).values().get())
    assert device.created_at is not None

    repeated_output = StringIO()
    with pytest.raises(CommandError, match="already exists"):
        call_command("create_demo_device", "pc-42", stdout=repeated_output)
    device.refresh_from_db()
    assert device.token_digest == hashlib.sha256(token.encode()).hexdigest()
    assert repeated_output.getvalue() == ""
    assert Device.objects.count() == 1


@pytest.mark.parametrize("device_id", ["", "bad/id", "x" * 65])
def test_invalid_device_id_is_rejected(device_id: str) -> None:
    output = StringIO()
    with pytest.raises(CommandError, match="Invalid device"):
        call_command("create_demo_device", device_id, stdout=output)
    assert not Device.objects.exists()
    assert output.getvalue() == ""


def test_task_defaults_and_persisted_result() -> None:
    device = Device.objects.create(id="pc-42", name="Demo", token_digest="a" * 64)
    task = Task.objects.create(device=device, action=Task.Action.COLLECT_SYSTEM_INFO)
    task.refresh_from_db()
    assert task.status == Task.Status.PENDING
    assert task.attempt == 0
    assert task.claim_token is None
    assert task.lease_until is None
    assert task.result is None
    assert task.error == ""
    assert task.completed_at is None
    assert task.created_at is not None
    task.result = {"os": "Linux", "cpu_count": 8}
    task.save(update_fields=["result"])
    assert Task.objects.get(pk=task.pk).result == {"os": "Linux", "cpu_count": 8}
    with pytest.raises(ProtectedError):
        device.delete()


@pytest.mark.parametrize(
    "changes",
    [{"action": "shell"}, {"status": "unknown"}, {"attempt": -1}],
)
def test_database_rejects_invalid_task_fields(changes: dict[str, object]) -> None:
    device = Device.objects.create(id="pc-42", name="Demo", token_digest="a" * 64)
    task = Task.objects.create(device=device, action=Task.Action.COLLECT_SYSTEM_INFO)
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.filter(pk=task.pk).update(**changes)
    task.refresh_from_db()
    assert task.action == Task.Action.COLLECT_SYSTEM_INFO
    assert task.status == Task.Status.PENDING
    assert task.attempt == 0


def test_migrations_create_claim_indexes_in_postgresql() -> None:
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, Task._meta.db_table)
    assert constraints["task_pending_idx"]["index"]
    assert constraints["task_pending_idx"]["columns"] == ["device_id", "status", "created_at", "id"]
    assert constraints["task_lease_idx"]["index"]
    assert constraints["task_lease_idx"]["columns"] == ["device_id", "status", "lease_until"]
