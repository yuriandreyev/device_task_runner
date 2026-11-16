from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TaskData:
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
