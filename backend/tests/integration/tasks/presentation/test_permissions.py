import hashlib

import pytest
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from backend.tasks.infrastructure.authentication import DeviceTokenAuthentication
from backend.tasks.infrastructure.models import Device
from backend.tasks.presentation.permissions import OwnsDevice


class DeviceEndpoint(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [OwnsDevice]

    def get(self, request: Request, device_id: str) -> Response:
        return Response({"device_id": device_id})


@pytest.mark.django_db
@pytest.mark.parametrize(
    "device_id,credential,status",
    [
        ("pc-42", "Bearer device-secret", 200),
        ("other", "Bearer device-secret", 403),
        ("pc-42", "Bearer invalid", 401),
        ("pc-42", "Bearer", 401),
        ("pc-42", "Bearer a b", 401),
        ("pc-42", "Token device-secret", 401),
        ("pc-42", "", 401),
    ],
)
def test_device_token_is_bound_to_its_device(device_id: str, credential: str, status: int) -> None:
    Device.objects.create(
        id="pc-42", name="Demo", token_digest=hashlib.sha256(b"device-secret").hexdigest()
    )
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION=credential)
    response = DeviceEndpoint.as_view()(request, device_id=device_id)
    assert response.status_code == status
    if status == 200:
        assert response.data == {"device_id": "pc-42"}
