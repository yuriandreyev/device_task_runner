from backend.tasks.application.ports import TaskRepository
from backend.tasks.domain.entities import Task, TaskResult


def complete_task(
    repository: TaskRepository, task_id: int, device_id: str, submission: TaskResult
) -> Task:
    if submission.status not in {"completed", "failed"}:
        raise ValueError("Unsupported terminal status")
    if not submission.claim_token:
        raise ValueError("Claim token is required")
    if submission.status == "completed" and (
        not isinstance(submission.result, dict) or submission.error
    ):
        raise ValueError("Completed tasks require a result object and no error")
    if submission.status == "failed" and (submission.result is not None or not submission.error):
        raise ValueError("Failed tasks require an error and no result")
    return repository.complete(task_id, device_id, submission)
