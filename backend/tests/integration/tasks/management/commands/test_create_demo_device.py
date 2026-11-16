import hashlib
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from backend.tasks.infrastructure.models import Device

pytestmark = pytest.mark.django_db


def test_create_demo_device_stores_only_digest_and_preserves_existing_token() -> None:
    output = StringIO()
    call_command("create_demo_device", "pc-42", stdout=output)
    lines = dict(line.split("=", 1) for line in output.getvalue().splitlines())
    assert lines["device_id"] == "pc-42"
    token = lines["device_token"]
    assert len(token) >= 43
    device = Device.objects.get(pk="pc-42")
    assert device.name == "pc-42"
    assert device.token_digest == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(Device.objects.filter(pk=device.pk).values().get())
    assert device.created_at is not None

    repeated_output = StringIO()
    with pytest.raises(CommandError, match="already exists"):
        call_command("create_demo_device", "pc-42", stdout=repeated_output)
    device.refresh_from_db()
    assert device.token_digest == hashlib.sha256(token.encode()).hexdigest()
    assert repeated_output.getvalue() == ""
    assert Device.objects.count() == 1


@pytest.mark.parametrize("device_id", ["", "bad/id", "x" * 65])
def test_invalid_device_id_is_rejected(device_id: str) -> None:
    output = StringIO()
    with pytest.raises(CommandError, match="Invalid device"):
        call_command("create_demo_device", device_id, stdout=output)
    assert not Device.objects.exists()
    assert output.getvalue() == ""
