from django.urls import path

from backend.tasks.infrastructure.storage.task_repository import DjangoTaskRepository
from backend.tasks.presentation.views import TaskDetailView, TaskListView
from backend.tasks.views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("api/tasks/", TaskListView.as_view(repository=DjangoTaskRepository()), name="task-create"),
    path(
        "api/tasks/<int:task_id>/",
        TaskDetailView.as_view(repository=DjangoTaskRepository()),
        name="task-detail",
    ),
]
