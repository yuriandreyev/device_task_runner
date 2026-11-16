from typing import Protocol

from backend.tasks.domain.entities import ClaimedTask, Task, TaskResult
from backend.tasks.domain.enums import PresenceStatus


class TaskRepository(Protocol):
    def create(self, device_id: str, action: str) -> Task: ...

    def get(self, task_id: int) -> Task: ...

    def claim(self, device_id: str) -> ClaimedTask | None: ...

    def complete(self, task_id: int, device_id: str, submission: TaskResult) -> Task: ...


class DeviceLookup(Protocol):
    def exists(self, device_id: str) -> bool: ...


class PresenceTracker(Protocol):
    def mark_seen(self, device_id: str) -> None: ...

    def get_status(self, device_id: str) -> PresenceStatus: ...
