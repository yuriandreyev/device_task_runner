"""Expose persistence models for Django's model discovery."""

from devices.infrastructure.models import Device, Task

__all__ = ["Device", "Task"]
