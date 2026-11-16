import hashlib
import hmac
from dataclasses import dataclass

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from backend.tasks.infrastructure.models import Device


@dataclass(frozen=True)
class DevicePrincipal:
    device_id: str
    is_authenticated: bool = True


class DeviceTokenAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[DevicePrincipal, None] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"bearer":
            return None
        if len(header) != 2 or len(header[1]) > 256:
            raise AuthenticationFailed("Invalid device token")
        digest = hashlib.sha256(header[1]).hexdigest()
        device = Device.objects.filter(token_digest=digest).first()
        if device is None or not hmac.compare_digest(device.token_digest, digest):
            raise AuthenticationFailed("Invalid device token")
        return DevicePrincipal(device.pk), None

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"
