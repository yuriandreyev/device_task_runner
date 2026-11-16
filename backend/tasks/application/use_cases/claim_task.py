from backend.tasks.application.ports import TaskRepository
from backend.tasks.domain.entities import ClaimedTask


def claim_task(repository: TaskRepository, device_id: str) -> ClaimedTask | None:
    return repository.claim(device_id)
