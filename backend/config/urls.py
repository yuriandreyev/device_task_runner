from django.conf import settings
from django.urls import path

from backend.tasks.infrastructure.presence import RedisPresence
from backend.tasks.infrastructure.storage.device_lookup import DjangoDeviceLookup
from backend.tasks.infrastructure.storage.task_repository import DjangoTaskRepository
from backend.tasks.presentation.views import (
    ClaimTaskView,
    DevicePresenceView,
    TaskDetailView,
    TaskListView,
    TaskResultView,
)
from backend.tasks.views import health

presence = RedisPresence.from_url(settings.REDIS_URL)

urlpatterns = [
    path(
        "api/devices/<slug:device_id>/presence/",
        DevicePresenceView.as_view(devices=DjangoDeviceLookup(), presence=presence),
        name="device-presence",
    ),
    path("health/", health, name="health"),
    path(
        "api/agents/<slug:device_id>/claim/",
        ClaimTaskView.as_view(repository=DjangoTaskRepository(), presence=presence),
        name="task-claim",
    ),
    path(
        "api/tasks/<int:task_id>/result/",
        TaskResultView.as_view(repository=DjangoTaskRepository(), presence=presence),
        name="task-result",
    ),
    path("api/tasks/", TaskListView.as_view(repository=DjangoTaskRepository()), name="task-create"),
    path(
        "api/tasks/<int:task_id>/",
        TaskDetailView.as_view(repository=DjangoTaskRepository()),
        name="task-detail",
    ),
]
