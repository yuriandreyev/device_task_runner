"""Expose persistence models for Django's model discovery."""

from backend.tasks.infrastructure.models import Device, Task

__all__ = ["Device", "Task"]
