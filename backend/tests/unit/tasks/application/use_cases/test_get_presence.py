from unittest.mock import Mock

import pytest

from backend.tasks.application.ports import DeviceLookup, PresenceTracker
from backend.tasks.application.use_cases.get_presence import get_presence
from backend.tasks.domain.enums import PresenceStatus
from backend.tasks.domain.exceptions import DeviceNotFound


@pytest.mark.parametrize("status", list(PresenceStatus))
def test_existing_device_presence_uses_the_presence_port(status: PresenceStatus) -> None:
    devices = Mock(spec=DeviceLookup)
    devices.exists.return_value = True
    presence = Mock(spec=PresenceTracker)
    presence.get_status.return_value = status
    result = get_presence(devices, presence, "pc-42")
    assert result.device_id == "pc-42"
    assert result.status is status
    devices.exists.assert_called_once_with("pc-42")
    presence.get_status.assert_called_once_with("pc-42")


def test_missing_device_does_not_query_presence() -> None:
    devices = Mock(spec=DeviceLookup)
    devices.exists.return_value = False
    presence = Mock(spec=PresenceTracker)
    with pytest.raises(DeviceNotFound):
        get_presence(devices, presence, "missing")
    presence.get_status.assert_not_called()
