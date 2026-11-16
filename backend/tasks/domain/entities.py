from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Task:
    id: int
    device_id: str
    action: str
    status: str
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
    status: str
    result: object = None
    error: str = ""
