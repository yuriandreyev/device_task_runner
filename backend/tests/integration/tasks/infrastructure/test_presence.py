import os
import time
from collections.abc import Iterator
from unittest.mock import Mock
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import ConnectionError

from backend.tasks.domain.enums import PresenceStatus
from backend.tasks.infrastructure.presence import RedisPresence


@pytest.fixture
def redis_presence() -> Iterator[tuple[RedisPresence, str]]:
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to run the real Redis presence integration tests")
    adapter = RedisPresence.from_url(url)
    assert adapter.client is not None
    adapter.client.ping()
    device_id = "test-" + uuid4().hex
    try:
        yield adapter, device_id
    finally:
        adapter.client.delete(f"agent:{device_id}:online")
        adapter.client.close()


def test_real_redis_ttl_refresh_and_marker_only_storage(
    redis_presence: tuple[RedisPresence, str],
) -> None:
    adapter, device_id = redis_presence
    assert adapter.client is not None
    key = f"agent:{device_id}:online"
    assert adapter.get_status(device_id) is PresenceStatus.OFFLINE
    adapter.mark_seen(device_id)
    assert adapter.client.get(key) == "1"
    ttl = adapter.client.ttl(key)
    assert isinstance(ttl, int) and 88 <= ttl <= 90
    # Reduce remaining lifetime so a refresh must restore the full production TTL.
    adapter.client.expire(key, 10)
    adapter.mark_seen(device_id)
    ttl = adapter.client.ttl(key)
    assert isinstance(ttl, int) and 88 <= ttl <= 90
    assert adapter.get_status(device_id) is PresenceStatus.ONLINE
    assert list(adapter.client.scan_iter(match=f"*{device_id}*")) == [key]


def test_real_redis_key_expires_to_offline(
    redis_presence: tuple[RedisPresence, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise real server expiration in one second; the production 90s is checked above.
    monkeypatch.setattr("backend.tasks.infrastructure.presence.PRESENCE_TTL_SECONDS", 1)
    adapter, device_id = redis_presence
    adapter.mark_seen(device_id)
    assert adapter.get_status(device_id) is PresenceStatus.ONLINE
    deadline = time.monotonic() + 3
    while adapter.get_status(device_id) is PresenceStatus.ONLINE and time.monotonic() < deadline:
        time.sleep(0.05)
    assert adapter.get_status(device_id) is PresenceStatus.OFFLINE


def test_missing_and_invalid_configuration_are_unknown(caplog: pytest.LogCaptureFixture) -> None:
    for url in ("", "invalid://secret@example.test"):
        adapter = RedisPresence.from_url(url)
        adapter.mark_seen("pc-42")
        assert adapter.get_status("pc-42") is PresenceStatus.UNKNOWN
    assert "secret" not in caplog.text


def test_redis_outage_and_recovery_does_not_cache_unknown_status() -> None:
    client = Mock(spec=Redis)
    client.exists.side_effect = [ConnectionError("private"), 0, 1]
    adapter = RedisPresence(client)
    assert adapter.get_status("pc-42") is PresenceStatus.UNKNOWN
    assert adapter.get_status("pc-42") is PresenceStatus.OFFLINE
    assert adapter.get_status("pc-42") is PresenceStatus.ONLINE
