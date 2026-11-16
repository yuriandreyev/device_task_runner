from backend.tasks.application.ports import TaskRepository
from backend.tasks.domain.entities import Task


def create_task(repository: TaskRepository, device_id: str, action: str) -> Task:
    if action != "collect_system_info":
        raise ValueError("Unsupported task action")
    return repository.create(device_id, action)
