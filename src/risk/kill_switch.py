"""Kill switch — halt trading on repeated API errors or anomalies."""

from __future__ import annotations

import time
from collections import deque

from src.bot.logging import get_logger

log = get_logger(__name__)


class KillSwitch:
    """Tracks API errors and triggers a kill switch if too many occur."""

    def __init__(self, max_errors: int = 10, window_seconds: int = 300):
        self.max_errors = max_errors
        self.window_seconds = window_seconds
        self._errors: deque[float] = deque()
        self._killed = False
        self._kill_reason: str | None = None

    def record_error(self, error_msg: str = "") -> None:
        now = time.time()
        self._errors.append(now)
        self._prune()

        if len(self._errors) >= self.max_errors:
            self._killed = True
            self._kill_reason = f"Too many errors ({len(self._errors)}/{self.max_errors} in {self.window_seconds}s)"
            log.critical("KILL SWITCH ACTIVATED: %s | last error: %s", self._kill_reason, error_msg)

    def _prune(self) -> None:
        cutoff = time.time() - self.window_seconds
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()

    @property
    def is_killed(self) -> bool:
        return self._killed

    @property
    def kill_reason(self) -> str | None:
        return self._kill_reason

    def reset(self) -> None:
        self._killed = False
        self._kill_reason = None
        self._errors.clear()
        log.info("Kill switch reset")

    @property
    def error_count(self) -> int:
        self._prune()
        return len(self._errors)
