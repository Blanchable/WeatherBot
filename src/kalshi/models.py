"""Pydantic models for Kalshi API payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class KalshiEvent(APIModel):
    event_ticker: str
    title: str | None = None
    status: str | None = None
    series_ticker: str | None = None
    close_time: datetime | None = None


class KalshiMarket(APIModel):
    ticker: str
    event_ticker: str | None = None
    title: str | None = None
    subtitle: str | None = Field(default=None, alias="sub_title")
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    status: str | None = None
    close_time: datetime | None = None
    expiration_time: datetime | None = None
    open_interest: int | None = 0
    volume: int | None = 0
    volume_24h: int | None = 0
    yes_bid: int | None = None
    yes_ask: int | None = None
    no_bid: int | None = None
    no_ask: int | None = None
    last_price: int | None = None
    strike_type: str | None = None
    floor_strike: float | None = None
    cap_strike: float | None = None


class OrderBookLevel(APIModel):
    price: int
    quantity: int


class MarketOrderBook(APIModel):
    ticker: str
    yes: list[OrderBookLevel] = Field(default_factory=list)
    no: list[OrderBookLevel] = Field(default_factory=list)

    @property
    def best_yes_bid(self) -> int | None:
        return max((level.price for level in self.yes), default=None)

    @property
    def best_yes_ask(self) -> int | None:
        best_no_bid = max((level.price for level in self.no), default=None)
        if best_no_bid is None:
            return None
        return 100 - best_no_bid


class KalshiOrder(APIModel):
    order_id: str | None = None
    client_order_id: str | None = None
    ticker: str | None = None
    side: str | None = None
    action: str | None = None
    yes_price: int | None = None
    count: int | None = None
    status: str | None = None
    created_time: datetime | None = None


class KalshiPosition(APIModel):
    ticker: str
    position: int = 0
    avg_price: int | None = None
    realized_pnl: float | None = 0.0
    market_exposure: float | None = 0.0


class PaginatedResponse(APIModel):
    cursor: str | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)

