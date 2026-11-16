from backend.tasks.application.ports import TaskRepository
from backend.tasks.domain.entities import TaskData


def get_task(repository: TaskRepository, task_id: int) -> TaskData:
    return repository.get(task_id)
