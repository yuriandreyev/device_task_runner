import pytest
from django.contrib.auth.models import Permission, User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


@pytest.fixture
def admin_client() -> APIClient:
    user = User.objects.create_user(username="operator")
    user.user_permissions.add(
        Permission.objects.get(codename="create_task", content_type__app_label="devices")
    )
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client
