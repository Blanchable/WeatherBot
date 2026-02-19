"""Kalshi API authentication — RSA key-based signing for Trade API v2."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils as asym_utils
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

from src.bot.config import get_settings
from src.bot.logging import get_logger

log = get_logger(__name__)


class KalshiAuth:
    """Generates signed headers for Kalshi Trade API v2 requests."""

    def __init__(
        self,
        key_id: str | None = None,
        private_key_path: str | None = None,
    ):
        settings = get_settings()
        self.key_id = key_id or settings.kalshi_key_id
        self._private_key_path = private_key_path or settings.kalshi_private_key_path
        self._private_key: PrivateKeyTypes | None = None

    def _load_key(self) -> PrivateKeyTypes:
        if self._private_key is None:
            key_path = Path(self._private_key_path)
            if not key_path.exists():
                raise FileNotFoundError(
                    f"Kalshi private key not found at {key_path}. "
                    "Generate one in your Kalshi account settings."
                )
            pem_data = key_path.read_bytes()
            self._private_key = serialization.load_pem_private_key(pem_data, password=None)
            log.info("Loaded Kalshi RSA key from %s", key_path)
        return self._private_key

    def sign_request(self, method: str, path: str, timestamp_ms: int | None = None) -> dict[str, str]:
        ts = timestamp_ms or int(time.time() * 1000)
        message = f"{ts}{method.upper()}{path}"
        key = self._load_key()

        signature = key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        sig_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "Content-Type": "application/json",
        }
