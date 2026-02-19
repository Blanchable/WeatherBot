"""Kalshi REST API client with authentication and rate limiting."""

import time
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import requests

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
    """Client for Kalshi Trading API v2."""

    def __init__(self, config: ApiConfig, credentials: Credentials):
        self.config = config
        self.credentials = credentials
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.member_id: Optional[str] = None
        self.rate_limiter = RateLimiter(max_calls=8, period=1.0)
        self._lock = threading.Lock()

    def _ensure_auth(self):
        if self.token and self.token_expiry and datetime.now(timezone.utc) < self.token_expiry:
            return
        self.login()

    def login(self) -> bool:
        try:
            resp = self.session.post(
                f"{self.config.base_url}/login",
                json={"email": self.credentials.email, "password": self.credentials.password},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("token")
            self.member_id = data.get("member_id")
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            # Tokens typically last ~24 hours; refresh well before expiry
            self.token_expiry = datetime.now(timezone.utc).replace(
                hour=23, minute=59, second=59
            )
            logger.info("Logged in to Kalshi (member_id=%s, demo=%s)", self.member_id, self.config.use_demo)
            return True
        except requests.RequestException as e:
            logger.error("Login failed: %s", e)
            return False

    def _request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        self._ensure_auth()
        self.rate_limiter.acquire()
        url = f"{self.config.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=15, **kwargs)
            if resp.status_code == 401:
                logger.warning("Token expired, re-authenticating")
                self.login()
                resp = self.session.request(method, url, timeout=15, **kwargs)
            resp.raise_for_status()
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
        data = self.get(f"/markets/{ticker}/trades", params={"limit": limit})
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
        # Use POST to batch cancel
        data = self.post("/portfolio/orders/batched", json_data={"action": "cancel_all", **params})
        # Fallback: cancel individually
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
