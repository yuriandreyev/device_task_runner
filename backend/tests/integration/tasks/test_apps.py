from django.apps import apps

from backend.tasks.infrastructure.models import Device, Task


def test_tasks_app_preserves_existing_database_identity() -> None:
    config = apps.get_app_config("devices")
    assert config.name == "backend.tasks"
    assert config.get_model("Device") is Device
    assert config.get_model("Task") is Task
    assert Device._meta.db_table == "devices_device"
    assert Task._meta.db_table == "devices_task"
