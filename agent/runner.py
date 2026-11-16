import logging
import random
import time
from collections.abc import Callable

from agent.actions import collect_system_info
from agent.client import AgentAPI, AgentError, PendingResult, ResultConflict, RetryableError

logger = logging.getLogger(__name__)


class Runner:
    def __init__(
        self,
        client: AgentAPI,
        collect: Callable[[], dict[str, object]] = collect_system_info,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.client = client
        self.collect = collect
        self.sleep = sleep
        self.jitter = jitter
        self.pending: PendingResult | None = None

    def step(self) -> bool:
        """Claim/execute once, or retry the exact pending bytes. False means retry later."""
        try:
            if self.pending is None:
                claim = self.client.claim()
                if claim is None:
                    logger.info("No task available")
                    return True
                if claim.action != "collect_system_info":
                    self.pending = PendingResult.failed(claim, "Unsupported action")
                else:
                    try:
                        self.pending = PendingResult.completed(claim, self.collect())
                    except Exception as exc:
                        # Exception messages may contain credentials or private host details.
                        self.pending = PendingResult.failed(
                            claim, f"System information collection failed ({type(exc).__name__})"
                        )
            self.client.submit(self.pending)
        except ResultConflict:
            logger.warning("Result conflict; discarding the stale attempt")
            self.pending = None
            return True
        except RetryableError:
            logger.warning("Request failed temporarily; retrying on the next poll")
            return False
        self.pending = None
        logger.info("Result accepted")
        return True

    def run(self, *, once: bool = False) -> int:
        # One-shot retries are bounded; continuous mode retains pending results in memory.
        attempts = 0
        while True:
            try:
                finished = self.step()
            except AgentError as exc:
                logger.error("%s", exc)
                return 1
            attempts += 1
            if once and finished:
                return 0
            if once and attempts >= 3:
                logger.error("One-shot retry limit reached")
                return 1
            self.sleep(self.jitter(24.0, 36.0))
