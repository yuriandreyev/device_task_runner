from dataclasses import dataclass
from datetime import datetime

from backend.tasks.domain.enums import TaskStatus


@dataclass(frozen=True)
class Task:
    id: int
    device_id: str
    action: str
    status: TaskStatus
    attempt: int
    result: object
    error: str


@dataclass(frozen=True)
class ClaimedTask:
    id: int
    action: str
    attempt: int
    claim_token: str
    lease_until: datetime


@dataclass(frozen=True)
class TaskResult:
    claim_token: str
    status: TaskStatus
    result: object = None
    error: str = ""
