from django.db import models

from backend.tasks.domain.enums import TaskStatus


class Device(models.Model):
    id = models.SlugField(primary_key=True, max_length=64)
    name = models.CharField(max_length=255)
    token_digest = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Task(models.Model):
    class Action(models.TextChoices):
        COLLECT_SYSTEM_INFO = "collect_system_info", "Collect system information"

    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="tasks")
    action = models.CharField(max_length=32, choices=Action.choices)
    status = models.CharField(
        max_length=16,
        choices=[(status.value, status.value.title()) for status in TaskStatus],
        default=TaskStatus.PENDING.value,
    )
    attempt = models.PositiveIntegerField(default=0)
    claim_token = models.CharField(max_length=64, null=True, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [("create_task", "Can create task")]
        indexes = [
            models.Index(fields=["device", "status", "created_at", "id"], name="task_pending_idx"),
            models.Index(fields=["device", "status", "lease_until"], name="task_lease_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action="collect_system_info"), name="task_valid_action"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[status.value for status in TaskStatus]),
                name="task_valid_status",
            ),
        ]
