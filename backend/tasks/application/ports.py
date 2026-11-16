from typing import Protocol

from backend.tasks.domain.entities import TaskData


class TaskRepository(Protocol):
    def create(self, device_id: str, action: str) -> TaskData: ...

    def get(self, task_id: int) -> TaskData: ...
