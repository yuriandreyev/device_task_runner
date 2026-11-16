from typing import Protocol

from backend.tasks.domain.entities import ClaimedTask, TaskData


class TaskRepository(Protocol):
    def create(self, device_id: str, action: str) -> TaskData: ...

    def get(self, task_id: int) -> TaskData: ...

    def claim(self, device_id: str) -> ClaimedTask | None: ...
