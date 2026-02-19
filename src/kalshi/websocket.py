"""Optional websocket streaming stub.

REST polling is sufficient for phase 1/2; this module is provided for future
latency-sensitive improvements.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class KalshiWebsocketConfig:
    ws_url: str
    enabled: bool = False


class KalshiWebsocketClient:
    def __init__(self, config: KalshiWebsocketConfig) -> None:
        self.config = config

    def connect(self) -> None:
        if not self.config.enabled:
            return
        raise NotImplementedError("Websocket support is intentionally deferred.")

