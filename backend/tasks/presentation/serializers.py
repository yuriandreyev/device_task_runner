from rest_framework import serializers

from backend.tasks.domain.entities import ClaimedTask, Task


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
