"""Kill switch triggered by API/system error bursts."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bot.config import BotConfig


@dataclass(slots=True)
class KillSwitchState:
    triggered: bool
    reason: str


class ErrorKillSwitch:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.error_times: deque[datetime] = deque()
        self.cancel_404_count = 0

    def _trim(self, now: datetime) -> None:
        window = timedelta(seconds=self.config.api_error_window_seconds)
        while self.error_times and now - self.error_times[0] > window:
            self.error_times.popleft()

    def record_error(self, now_utc: datetime | None = None) -> None:
        now = now_utc or datetime.now(UTC)
        self.error_times.append(now)
        self._trim(now)

    def record_cancel_404(self) -> None:
        self.cancel_404_count += 1

    def clear_cancel_404(self) -> None:
        self.cancel_404_count = 0

    def state(self, now_utc: datetime | None = None) -> KillSwitchState:
        now = now_utc or datetime.now(UTC)
        self._trim(now)
        if len(self.error_times) >= self.config.api_error_limit:
            return KillSwitchState(True, "api_error_rate_limit")
        if self.cancel_404_count >= 3:
            return KillSwitchState(True, "cancel_404_resync_required")
        return KillSwitchState(False, "ok")

