from django.urls import path

from backend.tasks.infrastructure.storage.task_repository import DjangoTaskRepository
from backend.tasks.presentation.views import ClaimTaskView, TaskDetailView, TaskListView
from backend.tasks.views import health

urlpatterns = [
    path("health/", health, name="health"),
    path(
        "api/agents/<slug:device_id>/claim/",
        ClaimTaskView.as_view(repository=DjangoTaskRepository()),
        name="task-claim",
    ),
    path("api/tasks/", TaskListView.as_view(repository=DjangoTaskRepository()), name="task-create"),
    path(
        "api/tasks/<int:task_id>/",
        TaskDetailView.as_view(repository=DjangoTaskRepository()),
        name="task-detail",
    ),
]
