from backend.tasks.application.ports import DeviceLookup, PresenceTracker
from backend.tasks.domain.entities import DevicePresence
from backend.tasks.domain.exceptions import DeviceNotFound


def get_presence(
    devices: DeviceLookup, presence: PresenceTracker, device_id: str
) -> DevicePresence:
    if not devices.exists(device_id):
        raise DeviceNotFound
    return DevicePresence(device_id, presence.get_status(device_id))
