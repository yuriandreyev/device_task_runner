from django.test import Client


def test_health(client: Client) -> None:
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_post(client: Client) -> None:
    assert client.post("/health/").status_code == 405
