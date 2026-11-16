import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    server_url: str
    device_id: str
    device_token: str = field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        env = os.environ if environ is None else environ
        url = env.get("SERVER_URL", "").rstrip("/")
        device_id = env.get("DEVICE_ID", "")
        token = env.get("DEVICE_TOKEN", "")
        try:
            parsed = urlsplit(url)
            valid_url = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and (parsed.port is None or parsed.port > 0)
                and not any(char.isspace() for char in url)
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValueError("SERVER_URL must be an HTTP(S) URL without credentials or query")
        if not re.fullmatch(r"[-a-zA-Z0-9_]{1,64}", device_id):
            raise ValueError("DEVICE_ID must be a device slug of 1 to 64 characters")
        if not token or len(token) > 256 or not all(33 <= ord(char) <= 126 for char in token):
            raise ValueError("DEVICE_TOKEN must be a nonempty ASCII token")
        return cls(url, device_id, token)
