from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from typing import Any
from unittest.mock import patch

import pytest
from django.db import connections
from django.utils import timezone

from backend.tasks.domain.entities import TaskResult
from backend.tasks.domain.enums import TaskStatus
from backend.tasks.domain.exceptions import ResultConflict
from backend.tasks.infrastructure.models import Device, Task
from backend.tasks.infrastructure.storage.task_repository import DjangoTaskRepository

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def expired_task() -> Task:
    assert connections["default"].vendor == "postgresql"
    Device.objects.create(id="pc-42", token_digest="a" * 64)
    return Task.objects.create(
        device_id="pc-42",
        action="collect_system_info",
        status=TaskStatus.RUNNING,
        attempt=1,
        claim_token="current-token",
        lease_until=timezone.now() - timedelta(seconds=1),
    )


@pytest.mark.parametrize("terminal", [TaskStatus.COMPLETED, TaskStatus.FAILED])
def test_failed_result_transaction_rolls_back_all_fields_and_can_be_retried(
    expired_task: Task, terminal: TaskStatus
) -> None:
    repository = DjangoTaskRepository()
    submission = TaskResult(
        claim_token="current-token",
        status=terminal,
        result={"os": "Linux"} if terminal == TaskStatus.COMPLETED else None,
        error="collection failed" if terminal == TaskStatus.FAILED else "",
    )
    snapshot = Task.objects.values().get(pk=expired_task.pk)
    original_save = Task.save

    def fail_after_save(instance: Task, **kwargs: Any) -> None:
        original_save(instance, **kwargs)
        raise RuntimeError("simulated failure before result commit")

    with (
        patch.object(Task, "save", autospec=True, side_effect=fail_after_save),
        pytest.raises(RuntimeError, match="before result commit"),
    ):
        repository.complete(expired_task.pk, "pc-42", submission)
    assert Task.objects.values().get(pk=expired_task.pk) == snapshot
    assert repository.complete(expired_task.pk, "pc-42", submission).status == terminal


@pytest.mark.parametrize("first_operation", ["complete", "reclaim"])
def test_result_and_reclaim_respect_the_attempt_selected_under_the_row_lock(
    expired_task: Task, first_operation: str
) -> None:
    repository = DjangoTaskRepository()
    submission = TaskResult("current-token", TaskStatus.COMPLETED, {"os": "Linux"})
    saved = Event()
    release = Event()
    contender_query = Event()
    original_save = Task.save

    def hold_first_write(instance: Task, **kwargs: Any) -> None:
        original_save(instance, **kwargs)
        if not saved.is_set():
            saved.set()
            assert release.wait(timeout=10)

    def before_query(execute: Any, sql: str, params: Any, many: bool, context: Any) -> Any:
        # Observe the ORM query immediately before execution; execute no raw SQL.
        contender_query.set()
        return execute(sql, params, many, context)

    def operate(operation: str, *, contender: bool = False) -> object:
        db = connections["default"]
        try:
            if contender:
                with db.execute_wrapper(before_query):
                    return perform(operation)
            return perform(operation)
        finally:
            db.close()

    def perform(operation: str) -> object:
        if operation == "reclaim":
            return repository.claim("pc-42")
        return repository.complete(expired_task.pk, "pc-42", submission)

    with (
        patch.object(Task, "save", autospec=True, side_effect=hold_first_write),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first = pool.submit(operate, first_operation)
        try:
            assert saved.wait(timeout=5)
            second = pool.submit(
                operate, "reclaim" if first_operation == "complete" else "complete", contender=True
            )
            assert contender_query.wait(timeout=5)
            if first_operation == "complete":
                # Claim skips the uncommitted terminal row without waiting for it.
                assert second.result(timeout=5) is None
        finally:
            release.set()
        first.result(timeout=5)
        if first_operation == "reclaim":
            with pytest.raises(ResultConflict):
                second.result(timeout=5)

    expired_task.refresh_from_db()
    if first_operation == "complete":
        assert expired_task.status == TaskStatus.COMPLETED
        assert expired_task.attempt == 1
        assert expired_task.result == {"os": "Linux"}
        assert expired_task.completed_at is not None
        assert repository.claim("pc-42") is None
    else:
        assert expired_task.status == TaskStatus.RUNNING
        assert expired_task.attempt == 2
        assert expired_task.claim_token != "current-token"
        assert expired_task.result is None
        assert expired_task.completed_at is None
        assert expired_task.claim_token is not None
        repository.complete(
            expired_task.pk,
            "pc-42",
            TaskResult(expired_task.claim_token, TaskStatus.COMPLETED, {"os": "Linux"}),
        )
