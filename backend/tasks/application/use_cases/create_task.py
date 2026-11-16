from backend.tasks.application.dto import TaskData
from backend.tasks.application.ports import TaskRepository


def create_task(repository: TaskRepository, device_id: str, action: str) -> TaskData:
    if action != "collect_system_info":
        raise ValueError("Unsupported task action")
    return repository.create(device_id, action)
