from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from backend.tasks.infrastructure.authentication import DevicePrincipal


class CanCreateTask(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user.is_authenticated and request.user.has_perm("devices.create_task"))


class OwnsDevice(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(request.user, DevicePrincipal) and (
            request.user.device_id == view.kwargs.get("device_id")
        )
