from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.tasks.application.ports import TaskRepository
from backend.tasks.application.use_cases.claim_task import claim_task
from backend.tasks.application.use_cases.complete_task import complete_task
from backend.tasks.application.use_cases.create_task import create_task
from backend.tasks.application.use_cases.get_task import get_task
from backend.tasks.domain.entities import TaskResult
from backend.tasks.domain.exceptions import (
    DeviceMismatch,
    DeviceNotFound,
    ResultConflict,
    TaskNotFound,
)
from backend.tasks.infrastructure.authentication import DevicePrincipal, DeviceTokenAuthentication
from backend.tasks.presentation.permissions import CanCreateTask, OwnsDevice
from backend.tasks.presentation.serializers import (
    ClaimedTaskSerializer,
    CreateTaskSerializer,
    TaskResultSerializer,
    TaskSerializer,
)


class TaskListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, CanCreateTask]
    repository: TaskRepository | None = None

    def post(self, request: Request) -> Response:
        serializer = CreateTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assert self.repository is not None
        try:
            task = create_task(self.repository, **serializer.validated_data)
        except DeviceNotFound as exc:
            raise NotFound("Device not found") from exc
        return Response(TaskSerializer(task).data, status=201)


class TaskDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    repository: TaskRepository | None = None

    def get(self, request: Request, task_id: int) -> Response:
        assert self.repository is not None
        try:
            task = get_task(self.repository, task_id)
        except TaskNotFound as exc:
            raise NotFound("Task not found") from exc
        return Response(TaskSerializer(task).data)


class ClaimTaskView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsAuthenticated, OwnsDevice]
    repository: TaskRepository | None = None

    def post(self, request: Request, device_id: str) -> Response:
        assert self.repository is not None
        task = claim_task(self.repository, device_id)
        if task is None:
            return Response(status=204)
        return Response(ClaimedTaskSerializer(task).data)


class TaskResultView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsAuthenticated]
    repository: TaskRepository | None = None

    def post(self, request: Request, task_id: int) -> Response:
        serializer = TaskResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assert self.repository is not None
        assert isinstance(request.user, DevicePrincipal)
        submission = TaskResult(**serializer.validated_data)
        try:
            task = complete_task(self.repository, task_id, request.user.device_id, submission)
        except TaskNotFound as exc:
            raise NotFound("Task not found") from exc
        except DeviceMismatch as exc:
            raise PermissionDenied("Task belongs to another device") from exc
        except ResultConflict:
            return Response({"detail": "Stale or conflicting result"}, status=409)
        return Response(TaskSerializer(task).data)
