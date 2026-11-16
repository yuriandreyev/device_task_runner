import json
from dataclasses import dataclass, field
from typing import Protocol, Self

import httpx

from agent.config import Config


class AgentError(Exception):
    """A permanent HTTP failure or invalid server response."""


class RetryableError(AgentError):
    """The request can be retried without changing its content."""


class ResultConflict(AgentError):
    """The server no longer accepts this attempt."""


@dataclass(frozen=True)
class Claim:
    id: int
    action: str
    claim_token: str = field(repr=False)


@dataclass(frozen=True)
class PendingResult:
    task_id: int
    content: bytes = field(repr=False)

    @classmethod
    def completed(cls, claim: Claim, result: dict[str, object]) -> Self:
        return cls._build(claim, {"status": "completed", "result": result})

    @classmethod
    def failed(cls, claim: Claim, error: str) -> Self:
        return cls._build(claim, {"status": "failed", "error": error})

    @classmethod
    def _build(cls, claim: Claim, fields: dict[str, object]) -> Self:
        payload = {"claim_token": claim.claim_token, **fields}
        return cls(claim.id, json.dumps(payload, allow_nan=False).encode())


class AgentAPI(Protocol):
    def claim(self) -> Claim | None: ...

    def submit(self, result: PendingResult) -> None: ...


class AgentClient:
    def __init__(self, config: Config, http: httpx.Client) -> None:
        self.config = config
        self.http = http

    def _post(self, path: str, content: bytes | None = None) -> httpx.Response:
        try:
            response = self.http.post(
                self.config.server_url + path,
                headers={
                    "Authorization": f"Bearer {self.config.device_token}",
                    "Content-Type": "application/json",
                },
                content=content,
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=False,
            )
        except httpx.TransportError:
            raise RetryableError("Network request failed") from None
        if response.status_code in {408, 429} or response.status_code >= 500:
            raise RetryableError("Server temporarily unavailable")
        return response

    def claim(self) -> Claim | None:
        response = self._post(f"/api/agents/{self.config.device_id}/claim/")
        if response.status_code == 204:
            return None
        if response.status_code != 200:
            raise AgentError(f"Claim rejected (HTTP {response.status_code})")
        try:
            data = response.json()
        except ValueError:
            raise AgentError("Invalid claim response") from None
        if not isinstance(data, dict):
            raise AgentError("Invalid claim response")
        task_id, action, token = data.get("id"), data.get("action"), data.get("claim_token")
        if (
            type(task_id) is not int
            or task_id <= 0
            or not isinstance(action, str)
            or not action
            or not isinstance(token, str)
            or not token
            or len(token) > 64
            or not token.isascii()
        ):
            raise AgentError("Invalid claim response")
        return Claim(task_id, action, token)

    def submit(self, result: PendingResult) -> None:
        response = self._post(f"/api/tasks/{result.task_id}/result/", result.content)
        if response.status_code == 409:
            raise ResultConflict("Result attempt is stale or conflicting")
        if response.status_code != 200:
            raise AgentError(f"Result rejected (HTTP {response.status_code})")
