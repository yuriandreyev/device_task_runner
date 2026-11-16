from backend.tasks.application.ports import TaskRepository
from backend.tasks.domain.entities import Task


def get_task(repository: TaskRepository, task_id: int) -> Task:
    return repository.get(task_id)
