from backend.tasks.infrastructure.models import Device


class DjangoDeviceLookup:
    def exists(self, device_id: str) -> bool:
        return Device.objects.filter(pk=device_id).exists()
