"""REST client for Kalshi Trade API v2."""

from __future__ import annotations

import logging
import random
import time
import uuid
from typing import Any, Iterable

import httpx

from kalshi.auth import KalshiAuth
from kalshi.models import KalshiEvent, KalshiMarket, KalshiOrder, KalshiPosition, MarketOrderBook

LOGGER = logging.getLogger(__name__)


class KalshiRestClient:
    def __init__(
        self,
        base_url: str,
        key_id: str = "",
        private_key_path: str = "",
        timeout: float = 10.0,
        max_retries: int = 5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.auth = KalshiAuth(key_id=key_id, private_key_path=private_key_path)

    def close(self) -> None:
        self.client.close()

    def _extract_items(self, payload: dict[str, Any], candidate_keys: Iterable[str]) -> list[dict[str, Any]]:
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth_required: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        if auth_required:
            auth_headers = self.auth.auth_headers(method=method, path=path, body=json_body)
            headers.update(auth_headers)

        for attempt in range(self.max_retries):
            response = self.client.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
                headers=headers,
            )

            if response.status_code < 400:
                return response.json() if response.content else {}

            should_retry = response.status_code == 429 or response.status_code >= 500
            if should_retry and attempt < self.max_retries - 1:
                backoff = min(8.0, (2**attempt) * 0.5) + random.uniform(0.05, 0.25)
                LOGGER.warning(
                    "kalshi request retry %s %s status=%s sleep=%.2f",
                    method,
                    path,
                    response.status_code,
                    backoff,
                )
                time.sleep(backoff)
                continue

            response.raise_for_status()

        raise RuntimeError(f"Kalshi request failed after retries: {method} {path}")

    def _paginate(
        self,
        path: str,
        *,
        limit: int,
        params: dict[str, Any] | None = None,
        item_keys: Iterable[str] = ("data",),
    ) -> list[dict[str, Any]]:
        cursor: str | None = None
        all_items: list[dict[str, Any]] = []
        page_params = dict(params or {})
        page_params["limit"] = limit

        while True:
            if cursor:
                page_params["cursor"] = cursor
            response = self._request("GET", path, params=page_params, auth_required=True)
            all_items.extend(self._extract_items(response, item_keys))
            cursor = response.get("cursor")
            if not cursor:
                break
        return all_items

    def get_events(self, status: str | None = "open", limit: int = 200) -> list[KalshiEvent]:
        limit = min(limit, 200)
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        raw_items = self._paginate("/events", limit=limit, params=params, item_keys=("events", "data"))
        return [KalshiEvent.model_validate(item) for item in raw_items]

    def get_markets(
        self,
        status: str | None = "open",
        limit: int = 1000,
        event_ticker: str | None = None,
    ) -> list[KalshiMarket]:
        limit = min(limit, 1000)
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if event_ticker:
            params["event_ticker"] = event_ticker

        raw_items = self._paginate("/markets", limit=limit, params=params, item_keys=("markets", "data"))
        return [KalshiMarket.model_validate(item) for item in raw_items]

    def get_orderbook(self, ticker: str) -> MarketOrderBook:
        try:
            response = self._request("GET", f"/markets/{ticker}/orderbook", auth_required=True)
            if "orderbook" in response and isinstance(response["orderbook"], dict):
                data = response["orderbook"]
            else:
                data = response
            if "ticker" not in data:
                data["ticker"] = ticker
            return MarketOrderBook.model_validate(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise

        fallback_market = next((m for m in self.get_markets(status="open") if m.ticker == ticker), None)
        if fallback_market is None:
            raise RuntimeError(f"Could not fetch orderbook or fallback market for ticker={ticker}")

        yes_levels = []
        no_levels = []
        if fallback_market.yes_bid is not None:
            yes_levels.append({"price": int(fallback_market.yes_bid), "quantity": 1})
        if fallback_market.yes_ask is not None:
            no_levels.append({"price": int(100 - fallback_market.yes_ask), "quantity": 1})
        return MarketOrderBook.model_validate(
            {
                "ticker": ticker,
                "yes": yes_levels,
                "no": no_levels,
            }
        )

    def place_order(
        self,
        *,
        ticker: str,
        side: str,
        action: str,
        count: int,
        yes_price: int,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
    ) -> KalshiOrder:
        payload: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": "limit",
            "yes_price": yes_price,
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        if expiration_ts:
            payload["expiration_ts"] = expiration_ts

        response = self._request(
            "POST",
            "/portfolio/orders",
            json_body=payload,
            auth_required=True,
            idempotency_key=str(uuid.uuid4()),
        )
        order_payload = response.get("order", response)
        return KalshiOrder.model_validate(order_payload)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/portfolio/orders/{order_id}", auth_required=True)

    def get_positions(self) -> list[KalshiPosition]:
        response = self._request("GET", "/portfolio/positions", auth_required=True)
        raw_items = self._extract_items(response, ("positions", "data"))
        return [KalshiPosition.model_validate(item) for item in raw_items]

    def get_orders(self, status: str | None = None) -> list[KalshiOrder]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        response = self._request("GET", "/portfolio/orders", params=params, auth_required=True)
        raw_items = self._extract_items(response, ("orders", "data"))
        return [KalshiOrder.model_validate(item) for item in raw_items]

