"""Pydantic models for Kalshi API objects."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Market(BaseModel):
    ticker: str
    event_ticker: str = ""
    title: str = ""
    subtitle: str = ""
    status: str = ""
    close_time: str = ""
    expiration_time: str = ""
    yes_bid: int = 0
    yes_ask: int = 0
    no_bid: int = 0
    no_ask: int = 0
    last_price: int = 0
    volume: int = 0
    volume_24h: int = 0
    open_interest: int = 0
    result: str = ""
    category: str = ""
    yes_sub_title: str = ""
    no_sub_title: str = ""
    open_time: str = ""
    rules_primary: str = ""
    settlement_value: Optional[int] = None

    @property
    def mid_price(self) -> float:
        if self.yes_bid > 0 and self.yes_ask > 0:
            return (self.yes_bid + self.yes_ask) / 2.0
        return float(self.last_price)

    @property
    def spread(self) -> int:
        if self.yes_bid > 0 and self.yes_ask > 0:
            return self.yes_ask - self.yes_bid
        return 99


class Event(BaseModel):
    event_ticker: str
    title: str = ""
    category: str = ""
    sub_title: str = ""
    series_ticker: str = ""
    markets: list[Market] = Field(default_factory=list)


class OrderRequest(BaseModel):
    ticker: str
    action: str  # 'buy' or 'sell'
    side: str  # 'yes' or 'no'
    type: str = "limit"
    count: int
    yes_price: Optional[int] = None
    no_price: Optional[int] = None
    expiration_ts: Optional[int] = None
    sell_position_floor: Optional[int] = None
    buy_max_cost: Optional[int] = None


class OrderResponse(BaseModel):
    order_id: str = ""
    ticker: str = ""
    status: str = ""
    action: str = ""
    side: str = ""
    yes_price: int = 0
    no_price: int = 0
    count: int = 0
    remaining_count: int = 0
    created_time: str = ""
    place_count: int = 0
    taker_fill_count: int = 0
    taker_fill_cost: int = 0
    maker_fill_count: int = 0
    maker_fill_cost: int = 0


class Position(BaseModel):
    ticker: str = ""
    market_exposure: int = 0
    rest_exposure: int = 0
    fees_paid: int = 0
    total_traded: int = 0
    realized_pnl: int = 0
    position: int = 0
    yes_count: int = Field(0, alias="yes_sub_total")
    no_count: int = Field(0, alias="no_sub_total")

    model_config = {"populate_by_name": True}


class OrderBookLevel(BaseModel):
    price: int
    quantity: int


class OrderBook(BaseModel):
    yes: list[list[int]] = Field(default_factory=list)
    no: list[list[int]] = Field(default_factory=list)

    @property
    def best_yes_bid(self) -> int:
        if self.yes:
            return max(lvl[0] for lvl in self.yes)
        return 0

    @property
    def best_yes_ask(self) -> int:
        if self.no:
            best_no_bid = max(lvl[0] for lvl in self.no)
            return 100 - best_no_bid
        return 100

    @property
    def spread(self) -> int:
        return self.best_yes_ask - self.best_yes_bid
