import pytest


@pytest.fixture(autouse=True)
def isolate_presence_from_configured_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    # Tests must not write presence markers to a developer's configured Redis.
    from backend.config.urls import presence

    monkeypatch.setattr(presence, "client", None)
