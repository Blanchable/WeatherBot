"""Kalshi Trade API v2 — REST client with pagination, rate-limiting, retries."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import httpx

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.kalshi.auth import KalshiAuth
from src.kalshi.models import (
    Event,
    Market,
    OrderBook,
    OrderRequest,
    OrderResponse,
    Position,
)

log = get_logger(__name__)

_MAX_RETRIES = 4
_RETRY_BASE_SECONDS = 1.0


class KalshiClient:
    """Async REST client for Kalshi Trade API v2."""

    def __init__(self, auth: KalshiAuth | None = None):
        self.settings = get_settings()
        self.base_url = self.settings.kalshi_rest_base.rstrip("/")
        self.auth = auth or KalshiAuth()
        self._client: httpx.AsyncClient | None = None
        self._rate_limit_until: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()

        now = time.time()
        if now < self._rate_limit_until:
            wait = self._rate_limit_until - now
            log.warning("Rate-limited, sleeping %.1fs", wait)
            await asyncio.sleep(wait)

        headers = self.auth.sign_request(method, path)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await client.request(
                    method,
                    self._url(path),
                    params=params,
                    json=json_body,
                    headers=headers,
                )

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2))
                    self._rate_limit_until = time.time() + retry_after
                    log.warning("429 rate-limited, retry after %.1fs (attempt %d)", retry_after, attempt)
                    await asyncio.sleep(retry_after + 0.5 * attempt)
                    headers = self.auth.sign_request(method, path)
                    continue

                if resp.status_code >= 500:
                    wait = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                    log.warning("Server error %d, retrying in %.1fs", resp.status_code, wait)
                    await asyncio.sleep(wait)
                    headers = self.auth.sign_request(method, path)
                    continue

                resp.raise_for_status()
                return resp.json() if resp.content else {}

            except httpx.TransportError as exc:
                wait = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                log.warning("Transport error: %s, retrying in %.1fs", exc, wait)
                await asyncio.sleep(wait)
                headers = self.auth.sign_request(method, path)

        raise RuntimeError(f"Request failed after {_MAX_RETRIES} retries: {method} {path}")

    # ── Pagination helper ───────────────────────────────────

    async def _paginate(
        self,
        method: str,
        path: str,
        result_key: str,
        params: dict | None = None,
        limit: int = 200,
    ) -> list[dict]:
        params = dict(params or {})
        params["limit"] = limit
        results: list[dict] = []
        cursor: str | None = None

        while True:
            if cursor:
                params["cursor"] = cursor
            data = await self._request(method, path, params=params)
            items = data.get(result_key, [])
            results.extend(items)
            cursor = data.get("cursor")
            if not cursor or len(items) < limit:
                break

        return results

    # ── Events ──────────────────────────────────────────────

    async def get_events(
        self,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool = True,
        limit: int = 200,
    ) -> list[Event]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        raw = await self._paginate("GET", "/events", "events", params=params, limit=limit)
        return [Event.model_validate(e) for e in raw]

    # ── Markets ─────────────────────────────────────────────

    async def get_markets(
        self,
        status: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        tickers: list[str] | None = None,
        limit: int = 1000,
    ) -> list[Market]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if tickers:
            params["tickers"] = ",".join(tickers)
        raw = await self._paginate("GET", "/markets", "markets", params=params, limit=limit)
        return [Market.model_validate(m) for m in raw]

    async def get_market(self, ticker: str) -> Market:
        data = await self._request("GET", f"/markets/{ticker}")
        return Market.model_validate(data.get("market", data))

    async def get_orderbook(self, ticker: str, depth: int = 10) -> OrderBook:
        data = await self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})
        return OrderBook.model_validate(data.get("orderbook", data))

    # ── Orders ──────────────────────────────────────────────

    async def place_order(self, req: OrderRequest) -> OrderResponse:
        body = req.model_dump(exclude_none=True)
        idem_key = str(uuid.uuid4())
        data = await self._request(
            "POST", "/portfolio/orders", json_body=body, idempotency_key=idem_key
        )
        return OrderResponse.model_validate(data.get("order", data))

    async def cancel_order(self, order_id: str) -> bool:
        try:
            await self._request("DELETE", f"/portfolio/orders/{order_id}")
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                log.warning("Order %s not found (already filled/cancelled?)", order_id)
                return False
            raise

    async def get_orders(
        self,
        ticker: str | None = None,
        status: str | None = None,
    ) -> list[OrderResponse]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        raw = await self._paginate("GET", "/portfolio/orders", "orders", params=params)
        return [OrderResponse.model_validate(o) for o in raw]

    # ── Positions ───────────────────────────────────────────

    async def get_positions(
        self,
        ticker: str | None = None,
        settlement_status: str | None = None,
    ) -> list[Position]:
        params: dict[str, Any] = {}
        if ticker:
            params["ticker"] = ticker
        if settlement_status:
            params["settlement_status"] = settlement_status
        raw = await self._paginate(
            "GET", "/portfolio/positions", "market_positions", params=params
        )
        return [Position.model_validate(p) for p in raw]

    # ── Balance ─────────────────────────────────────────────

    async def get_balance(self) -> float:
        data = await self._request("GET", "/portfolio/balance")
        return data.get("balance", 0) / 100.0
