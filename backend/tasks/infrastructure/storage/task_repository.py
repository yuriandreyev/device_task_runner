from django.db import transaction

from backend.tasks.application.dto import TaskData
from backend.tasks.application.ports import DeviceNotFound, TaskNotFound
from backend.tasks.infrastructure.models import Device, Task


def task_data(task: Task) -> TaskData:
    return TaskData(
        id=task.pk,
        device_id=task.device_id,
        action=task.action,
        status=task.status,
        attempt=task.attempt,
        result=task.result,
        error=task.error,
    )


class DjangoTaskRepository:
    def create(self, device_id: str, action: str) -> TaskData:
        with transaction.atomic():
            try:
                device = Device.objects.select_for_update().get(pk=device_id)
            except Device.DoesNotExist as exc:
                raise DeviceNotFound from exc
            return task_data(Task.objects.create(device=device, action=action))

    def get(self, task_id: int) -> TaskData:
        try:
            task = Task.objects.get(pk=task_id)
        except Task.DoesNotExist as exc:
            raise TaskNotFound from exc
        return task_data(task)
