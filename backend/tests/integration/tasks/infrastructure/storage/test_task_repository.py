from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any
from unittest.mock import patch

import pytest
from django.db import connection, connections, transaction

from backend.tasks.infrastructure.models import Device, Task
from backend.tasks.infrastructure.storage.task_repository import DjangoTaskRepository

pytestmark = pytest.mark.django_db(transaction=True)


def test_claim_skips_locked_task_without_waiting() -> None:
    assert connection.vendor == "postgresql"
    Device.objects.create(id="pc-42", name="Demo", token_digest="a" * 64)
    locked_task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    available_task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    locked = Event()
    release = Event()

    def hold_lock() -> None:
        try:
            with transaction.atomic():
                Task.objects.select_for_update().get(pk=locked_task.pk)
                locked.set()
                assert release.wait(timeout=10)
        finally:
            connections.close_all()

    def claim() -> int | None:
        try:
            result = DjangoTaskRepository().claim("pc-42")
            return result.id if result else None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(hold_lock)
        try:
            assert locked.wait(timeout=5)
            assert pool.submit(claim).result(timeout=5) == available_task.pk
        finally:
            release.set()
        holder.result(timeout=5)
    locked_task.refresh_from_db()
    assert locked_task.status == "pending"
    assert locked_task.attempt == 0
    available_task.refresh_from_db()
    assert available_task.status == "running"


def test_failed_claim_rolls_back_attempt_and_credentials() -> None:
    Device.objects.create(id="pc-42", name="Demo", token_digest="a" * 64)
    task = Task.objects.create(device_id="pc-42", action="collect_system_info")
    original_save = Task.save

    def fail_after_save(instance: Task, **kwargs: Any) -> None:
        original_save(instance, **kwargs)
        raise RuntimeError("simulated failure before commit")

    with patch.object(Task, "save", autospec=True, side_effect=fail_after_save):
        with pytest.raises(RuntimeError, match="simulated failure"):
            DjangoTaskRepository().claim("pc-42")
    task.refresh_from_db()
    assert task.status == "pending"
    assert task.attempt == 0
    assert task.claim_token is None
    assert task.lease_until is None
