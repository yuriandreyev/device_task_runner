from backend.tasks.application.dto import TaskData
from backend.tasks.application.ports import TaskRepository


def get_task(repository: TaskRepository, task_id: int) -> TaskData:
    return repository.get(task_id)
