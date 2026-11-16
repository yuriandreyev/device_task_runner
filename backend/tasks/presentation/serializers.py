from rest_framework import serializers

from backend.tasks.domain.entities import ClaimedTask, Task
from backend.tasks.domain.enums import TaskStatus


class CreateTaskSerializer(serializers.Serializer[dict[str, str]]):
    device_id = serializers.SlugField(max_length=64)
    action = serializers.ChoiceField(choices=["collect_system_info"])


class TaskSerializer(serializers.Serializer[Task]):
    id = serializers.IntegerField(read_only=True)
    device_id = serializers.CharField(read_only=True)
    action = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    attempt = serializers.IntegerField(read_only=True)
    result = serializers.JSONField(read_only=True)
    error = serializers.CharField(read_only=True)


class ClaimedTaskSerializer(serializers.Serializer[ClaimedTask]):
    id = serializers.IntegerField(read_only=True)
    action = serializers.CharField(read_only=True)
    attempt = serializers.IntegerField(read_only=True)
    claim_token = serializers.CharField(read_only=True)
    lease_until = serializers.DateTimeField(read_only=True)


class TaskResultSerializer(serializers.Serializer[dict[str, object]]):
    claim_token = serializers.CharField(max_length=64, trim_whitespace=False)
    status = serializers.ChoiceField(choices=[TaskStatus.COMPLETED, TaskStatus.FAILED])
    result = serializers.JSONField(required=False)
    error = serializers.CharField(required=False, trim_whitespace=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if set(self.initial_data) - {"claim_token", "status", "result", "error"}:
            raise serializers.ValidationError("Unknown fields")
        if attrs["status"] == TaskStatus.COMPLETED:
            if not isinstance(attrs.get("result"), dict) or "error" in attrs:
                raise serializers.ValidationError("Provide a result object and no error")
        elif "result" in attrs or not attrs.get("error"):
            raise serializers.ValidationError("Provide an error and no result")
        attrs["status"] = TaskStatus(str(attrs["status"]))
        return attrs
