from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.tasks"
    # Preserve migration history, table names and content types on existing databases.
    label = "devices"
