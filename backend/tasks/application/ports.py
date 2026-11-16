from typing import Protocol

from backend.tasks.application.dto import TaskData


class DeviceNotFound(Exception):
    pass


class TaskNotFound(Exception):
    pass


class TaskRepository(Protocol):
    def create(self, device_id: str, action: str) -> TaskData: ...

    def get(self, task_id: int) -> TaskData: ...
