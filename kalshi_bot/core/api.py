"""Kalshi REST API client with RSA-PSS per-request signing."""

import base64
import time
import logging
import threading
from typing import Any, Optional

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from kalshi_bot.core.config import ApiConfig, Credentials

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, max_calls: int = 10, period: float = 1.0):
        self.max_calls = max_calls
        self.period = period
        self.calls: list[float] = []
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self.calls.append(time.monotonic())


class KalshiApiClient:
    """Client for Kalshi Trading API v2 with RSA-PSS key authentication.

    Each request is signed per Kalshi's scheme:
      - Message = timestamp_ms + METHOD + path (without query params)
      - Signature = RSA-PSS (MGF1-SHA256, salt=digest_length) over message
      - Three headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP
    """

    def __init__(self, config: ApiConfig, credentials: Credentials):
        self.config = config
        self.credentials = credentials
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        self._private_key = None
        self.rate_limiter = RateLimiter(max_calls=8, period=1.0)

    def login(self) -> bool:
        """Load the private key and verify auth by hitting an authenticated endpoint."""
        self._private_key = self.credentials.load_private_key()
        if self._private_key is None:
            logger.error("Failed to load RSA private key from: %s", self.credentials.private_key_path)
            return False

        try:
            # Use portfolio/balance (requires auth) to verify the key is valid
            balance = self.get_balance()
            if balance is not None:
                logger.info(
                    "Connected to Kalshi (key=%s..., demo=%s, balance=$%.2f)",
                    self.credentials.api_key_id[:8] if len(self.credentials.api_key_id) >= 8 else self.credentials.api_key_id,
                    self.config.use_demo,
                    balance / 100,
                )
                return True
            logger.error("Auth failed - check your API Key ID and private key .pem file")
            return False
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False

    def _sign_request(self, method: str, path: str) -> dict[str, str]:
        """Generate the three Kalshi auth headers by RSA-PSS signing the request."""
        timestamp_ms = str(int(time.time() * 1000))

        # Strip query params from path for signing (Kalshi requirement)
        sign_path = path.split("?")[0]
        message = (timestamp_ms + method.upper() + sign_path).encode("utf-8")

        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        sig_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": self.credentials.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": sig_b64,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }

    def _request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        if self._private_key is None:
            logger.error("Cannot make request - private key not loaded")
            return None

        self.rate_limiter.acquire()

        full_path = self.config.api_prefix + path
        url = self.config.host + full_path
        auth_headers = self._sign_request(method, full_path)

        try:
            resp = self.session.request(
                method, url, timeout=15, headers=auth_headers, **kwargs,
            )
            if resp.status_code == 401:
                logger.error(
                    "Auth failed (401) for %s %s - check API key and private key. Body: %s",
                    method, path, resp.text[:200],
                )
                return None
            if not resp.ok:
                logger.error(
                    "API %s %s returned %d: %s",
                    method, path, resp.status_code, resp.text[:300],
                )
                return None
            if resp.content:
                return resp.json()
            return {}
        except requests.RequestException as e:
            logger.error("API %s %s failed: %s", method, path, e)
            return None

    def get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        return self._request("GET", path, params=params)

    def post(self, path: str, json_data: Optional[dict] = None) -> Optional[dict]:
        return self._request("POST", path, json=json_data)

    def delete(self, path: str) -> Optional[dict]:
        return self._request("DELETE", path)

    # ── Account ─────────────────────────────────────────────────
    def get_balance(self) -> Optional[int]:
        data = self.get("/portfolio/balance")
        if data:
            return data.get("balance")
        return None

    def get_positions(self, **kwargs) -> list[dict]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        data = self.get("/portfolio/positions", params=params)
        if data:
            return data.get("market_positions", [])
        return []

    def get_portfolio_settlements(self, limit: int = 100) -> list[dict]:
        data = self.get("/portfolio/settlements", params={"limit": limit})
        if data:
            return data.get("settlements", [])
        return []

    # ── Markets ─────────────────────────────────────────────────
    def get_exchange_status(self) -> Optional[dict]:
        return self.get("/exchange/status")

    def get_events(self, **kwargs) -> list[dict]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        data = self.get("/events", params=params)
        if data:
            return data.get("events", [])
        return []

    def get_event(self, event_ticker: str) -> Optional[dict]:
        data = self.get(f"/events/{event_ticker}")
        if data:
            return data.get("event", data)
        return None

    def get_markets(self, **kwargs) -> list[dict]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        data = self.get("/markets", params=params)
        if data:
            return data.get("markets", [])
        return []

    def get_market(self, ticker: str) -> Optional[dict]:
        data = self.get(f"/markets/{ticker}")
        if data:
            return data.get("market", data)
        return None

    def get_orderbook(self, ticker: str, depth: int = 10) -> Optional[dict]:
        data = self.get(f"/markets/{ticker}/orderbook", params={"depth": depth})
        if data:
            return data.get("orderbook", data)
        return None

    def get_series(self, series_ticker: str) -> Optional[dict]:
        return self.get(f"/series/{series_ticker}")

    def get_trades(self, ticker: str, limit: int = 50) -> list[dict]:
        data = self.get("/markets/trades", params={"ticker": ticker, "limit": limit})
        if data:
            return data.get("trades", [])
        return []

    # ── Orders ──────────────────────────────────────────────────
    def get_orders(self, **kwargs) -> list[dict]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        data = self.get("/portfolio/orders", params=params)
        if data:
            return data.get("orders", [])
        return []

    def place_order(
        self,
        ticker: str,
        side: str,
        action: str,
        order_type: str,
        count: int,
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
        client_order_id: Optional[str] = None,
        expiration_ts: Optional[int] = None,
    ) -> Optional[dict]:
        """Place an order on Kalshi.

        Args:
            ticker: Market ticker
            side: 'yes' or 'no'
            action: 'buy' or 'sell'
            order_type: 'limit' or 'market'
            count: Number of contracts
            yes_price: Price in cents (1-99) for yes side
            no_price: Price in cents (1-99) for no side
            client_order_id: Optional client-side order ID
            expiration_ts: Optional Unix timestamp for order expiry
        """
        payload: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "type": order_type,
            "count": count,
        }
        if yes_price is not None:
            payload["yes_price"] = yes_price
        if no_price is not None:
            payload["no_price"] = no_price
        if client_order_id:
            payload["client_order_id"] = client_order_id
        if expiration_ts:
            payload["expiration_ts"] = expiration_ts

        data = self.post("/portfolio/orders", json_data=payload)
        if data:
            return data.get("order", data)
        return None

    def cancel_order(self, order_id: str) -> Optional[dict]:
        return self.delete(f"/portfolio/orders/{order_id}")

    def batch_cancel_orders(self, market_ticker: Optional[str] = None) -> Optional[dict]:
        """Cancel all resting orders, optionally filtered by market."""
        params = {}
        if market_ticker:
            params["ticker"] = market_ticker
        data = self.post("/portfolio/orders/batched", json_data={"action": "cancel_all", **params})
        if data is None:
            orders = self.get_orders(ticker=market_ticker, status="resting")
            cancelled = 0
            for order in orders:
                oid = order.get("order_id")
                if oid:
                    self.cancel_order(oid)
                    cancelled += 1
            return {"cancelled": cancelled}
        return data

    def cancel_all_orders(self) -> int:
        """Cancel all resting orders across all markets."""
        orders = self.get_orders(status="resting")
        cancelled = 0
        for order in orders:
            oid = order.get("order_id")
            if oid:
                result = self.cancel_order(oid)
                if result is not None:
                    cancelled += 1
        return cancelled
