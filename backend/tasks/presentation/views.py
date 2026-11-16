from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.tasks.application.ports import TaskRepository
from backend.tasks.application.use_cases.create_task import create_task
from backend.tasks.application.use_cases.get_task import get_task
from backend.tasks.domain.exceptions import DeviceNotFound, TaskNotFound
from backend.tasks.presentation.permissions import CanCreateTask
from backend.tasks.presentation.serializers import CreateTaskSerializer, TaskSerializer


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
