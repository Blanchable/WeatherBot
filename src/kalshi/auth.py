"""Authentication helpers for Kalshi REST API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any


class KalshiAuth:
    """Build auth headers for Kalshi requests.

    The production API uses asymmetric signatures. This implementation supports
    RSA-PSS if `cryptography` is installed and falls back to HMAC for local
    testing with paper/demo integrations.
    """

    def __init__(self, key_id: str, private_key_path: str) -> None:
        self.key_id = key_id
        self.private_key_path = private_key_path
        self._cached_key_bytes: bytes | None = None

    def _load_key_bytes(self) -> bytes:
        if self._cached_key_bytes is not None:
            return self._cached_key_bytes
        if not self.private_key_path:
            raise ValueError("KALSHI_PRIVATE_KEY_PATH is required for live trading.")
        key_path = Path(self.private_key_path)
        self._cached_key_bytes = key_path.read_bytes()
        return self._cached_key_bytes

    def _serialize_body(self, body: dict[str, Any] | None) -> str:
        if not body:
            return ""
        return json.dumps(body, separators=(",", ":"), sort_keys=True)

    def _sign_payload(self, payload: str) -> str:
        key_bytes = self._load_key_bytes()
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            digest = hmac.new(key_bytes, payload.encode("utf-8"), hashlib.sha256).digest()
            return base64.b64encode(digest).decode("utf-8")

        private_key = serialization.load_pem_private_key(key_bytes, password=None)
        signature = private_key.sign(
            payload.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def auth_headers(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        if not self.key_id:
            return {}

        ts = str(timestamp_ms or int(time.time() * 1000))
        payload = f"{ts}{method.upper()}{path}{self._serialize_body(body)}"
        signature = self._sign_payload(payload)
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }

