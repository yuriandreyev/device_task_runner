import logging

from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from backend.tasks.domain.enums import PresenceStatus

logger = logging.getLogger(__name__)
PRESENCE_TTL_SECONDS = 90


class RedisPresence:
    def __init__(self, client: Redis | None) -> None:
        self.client = client

    @classmethod
    def from_url(cls, url: str) -> "RedisPresence":
        if not url:
            return cls(None)
        try:
            client = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                retry=Retry(NoBackoff(), 0),
            )
        except ValueError:
            logger.warning("Presence configuration is invalid; status is unknown")
            return cls(None)
        return cls(client)

    def mark_seen(self, device_id: str) -> None:
        if self.client is None:
            return
        try:
            self.client.set(f"agent:{device_id}:online", "1", ex=PRESENCE_TTL_SECONDS)
        except RedisError:
            logger.warning("Presence update unavailable")

    def get_status(self, device_id: str) -> PresenceStatus:
        if self.client is None:
            return PresenceStatus.UNKNOWN
        try:
            return (
                PresenceStatus.ONLINE
                if self.client.exists(f"agent:{device_id}:online")
                else PresenceStatus.OFFLINE
            )
        except RedisError:
            logger.warning("Presence read unavailable; status is unknown")
            return PresenceStatus.UNKNOWN
