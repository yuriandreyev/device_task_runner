from typing import Protocol

from backend.tasks.domain.entities import ClaimedTask, Task


class TaskRepository(Protocol):
    def create(self, device_id: str, action: str) -> Task: ...

    def get(self, task_id: int) -> Task: ...

    def claim(self, device_id: str) -> ClaimedTask | None: ...
