import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from backend.tasks.infrastructure.models import Device, Task

pytestmark = pytest.mark.django_db


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
