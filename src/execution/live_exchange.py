"""Live exchange adapter backed by Kalshi REST client."""

from __future__ import annotations

from kalshi.rest import KalshiRestClient


class KalshiLiveExchange:
    def __init__(self, client: KalshiRestClient) -> None:
        self.client = client

    def place_limit_order(
        self,
        *,
        ticker: str,
        side: str,
        action: str,
        price_cents: int,
        contracts: int,
        city_id: str = "",
    ) -> str:
        if side != "yes":
            raise ValueError("Live adapter currently supports YES-side orders only.")
        order = self.client.place_order(
            ticker=ticker,
            side=side,
            action=action,
            count=contracts,
            yes_price=price_cents,
        )
        if not order.order_id:
            raise RuntimeError("Kalshi did not return an order_id.")
        return order.order_id

    def cancel_order(self, order_id: str) -> None:
        self.client.cancel_order(order_id)

    def list_open_orders(self) -> list[dict]:
        orders = self.client.get_orders(status="open")
        return [order.model_dump() for order in orders]

