import hmac
import json
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from backend.tasks.domain.entities import ClaimedTask, Task, TaskResult
from backend.tasks.domain.exceptions import (
    DeviceMismatch,
    DeviceNotFound,
    ResultConflict,
    TaskNotFound,
)
from backend.tasks.infrastructure.models import Device
from backend.tasks.infrastructure.models import Task as TaskModel


def to_entity(task: TaskModel) -> Task:
    return Task(
        id=task.pk,
        device_id=task.device_id,
        action=task.action,
        status=task.status,
        attempt=task.attempt,
        result=task.result,
        error=task.error,
    )


class DjangoTaskRepository:
    def claim(self, device_id: str) -> ClaimedTask | None:
        # A claim must commit before its credentials can be returned to the agent.
        with transaction.atomic(durable=True):
            now = timezone.now()
            task = (
                TaskModel.objects.select_for_update(skip_locked=True)
                .filter(device_id=device_id)
                .filter(
                    Q(status=TaskModel.Status.PENDING)
                    | Q(status=TaskModel.Status.RUNNING, lease_until__lte=now)
                )
                .order_by("created_at", "id")
                .first()
            )
            if task is None:
                return None
            task.status = TaskModel.Status.RUNNING
            task.attempt += 1
            task.claim_token = secrets.token_urlsafe(32)
            task.lease_until = timezone.now() + timedelta(seconds=60)
            task.save(update_fields=["status", "attempt", "claim_token", "lease_until"])
            claimed = ClaimedTask(
                id=task.pk,
                action=task.action,
                attempt=task.attempt,
                claim_token=task.claim_token,
                lease_until=task.lease_until,
            )
        return claimed

    def complete(self, task_id: int, device_id: str, submission: TaskResult) -> Task:
        with transaction.atomic(durable=True):
            try:
                task = TaskModel.objects.select_for_update().get(pk=task_id)
            except TaskModel.DoesNotExist as exc:
                raise TaskNotFound from exc
            if task.device_id != device_id:
                raise DeviceMismatch
            if not task.claim_token or not hmac.compare_digest(
                task.claim_token.encode(), submission.claim_token.encode()
            ):
                raise ResultConflict
            if task.status in {"completed", "failed"}:
                # Ignore object key order without equating JSON true and 1.
                if (
                    task.status != submission.status
                    or json.dumps(task.result, sort_keys=True)
                    != json.dumps(submission.result, sort_keys=True)
                    or task.error != submission.error
                ):
                    raise ResultConflict
            elif task.status == "running":
                # Lease expiry alone does not invalidate the current attempt.
                task.status = submission.status
                task.result = submission.result
                task.error = submission.error
                task.completed_at = timezone.now()
                task.save(update_fields=["status", "result", "error", "completed_at"])
            else:
                raise ResultConflict
            result = to_entity(task)
        return result

    def create(self, device_id: str, action: str) -> Task:
        with transaction.atomic():
            try:
                device = Device.objects.select_for_update().get(pk=device_id)
            except Device.DoesNotExist as exc:
                raise DeviceNotFound from exc
            return to_entity(TaskModel.objects.create(device=device, action=action))

    def get(self, task_id: int) -> Task:
        try:
            task = TaskModel.objects.get(pk=task_id)
        except TaskModel.DoesNotExist as exc:
            raise TaskNotFound from exc
        return to_entity(task)
