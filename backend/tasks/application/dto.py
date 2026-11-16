from dataclasses import dataclass


@dataclass(frozen=True)
class TaskData:
    id: int
    device_id: str
    action: str
    status: str
    attempt: int
    result: object
    error: str
