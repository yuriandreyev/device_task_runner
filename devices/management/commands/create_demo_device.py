import hashlib
import secrets
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import IntegrityError, transaction

from devices.infrastructure.models import Device


class Command(BaseCommand):
    help = "Create a demo device and display its token once. Existing devices are unchanged."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("device_id")

    def handle(self, *args: Any, **options: Any) -> None:
        device_id = options["device_id"]
        token = secrets.token_urlsafe(32)
        device = Device(
            id=device_id,
            name=device_id,
            token_digest=hashlib.sha256(token.encode()).hexdigest(),
        )
        try:
            device.full_clean(validate_unique=False)
        except ValidationError as exc:
            raise CommandError(f"Invalid device: {exc}") from exc
        try:
            with transaction.atomic():
                device.save(force_insert=True)
        except IntegrityError as exc:
            raise CommandError("Device already exists; its token has not been changed.") from exc
        self.stdout.write(f"device_id={device.pk}")
        self.stdout.write(f"device_token={token}")
