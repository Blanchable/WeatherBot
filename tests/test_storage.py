"""Tests for the storage layer."""

import pytest
import tempfile
from pathlib import Path

from src.storage.db import Database


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "test.db")
        db.init_schema()
        yield db
        db.close()


class TestDatabase:
    def test_init_schema(self, db):
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {t["name"] for t in tables}
        assert "forecasts" in names
        assert "weather_markets" in names
        assert "orders" in names
        assert "positions" in names
        assert "fills" in names
        assert "daily_pnl" in names

    def test_save_and_get_forecast(self, db):
        db.save_forecast(
            city_id="NYC",
            forecast_date="2026-02-20",
            predicted_high=75.0,
            predicted_low=55.0,
            sigma=1.5,
        )
        result = db.get_latest_forecast("NYC", "2026-02-20")
        assert result is not None
        assert result["city_id"] == "NYC"
        assert result["predicted_high"] == 75.0
        assert result["predicted_low"] == 55.0

    def test_upsert_market(self, db):
        market = {
            "ticker": "TEST-1",
            "event_ticker": "EVT-1",
            "city": "NYC",
            "market_date": "2026-02-20",
            "market_type": "high_temp",
            "strike_low": 73.0,
            "strike_high": 77.0,
            "strike_op": "range",
            "close_time": "2026-02-20T23:00:00Z",
            "status": "open",
        }
        db.upsert_market(market)
        markets = db.get_open_markets()
        assert len(markets) == 1
        assert markets[0]["ticker"] == "TEST-1"

    def _insert_test_market(self, db):
        market = {
            "ticker": "TEST-1",
            "event_ticker": "EVT-1",
            "city": "NYC",
            "market_date": "2026-02-20",
            "market_type": "high_temp",
            "strike_low": 73.0,
            "strike_high": 77.0,
            "strike_op": "range",
            "close_time": "2026-02-20T23:00:00Z",
            "status": "open",
        }
        db.upsert_market(market)

    def test_save_and_get_order(self, db):
        self._insert_test_market(db)
        order = {
            "order_id": "order-123",
            "ticker": "TEST-1",
            "side": "yes",
            "action": "buy",
            "price_cents": 55,
            "quantity": 5,
            "is_paper": 1,
        }
        db.save_order(order)
        orders = db.get_open_orders(is_paper=True)
        assert len(orders) == 1
        assert orders[0]["order_id"] == "order-123"

    def test_update_order_status(self, db):
        self._insert_test_market(db)
        order = {
            "order_id": "order-456",
            "ticker": "TEST-1",
            "side": "yes",
            "action": "buy",
            "price_cents": 55,
            "quantity": 5,
            "is_paper": 1,
        }
        db.save_order(order)
        db.update_order_status("order-456", "filled", 5)
        orders = db.get_open_orders(is_paper=True)
        assert len(orders) == 0  # filled, no longer resting

    def test_upsert_position(self, db):
        pos = {
            "ticker": "TEST-1",
            "side": "yes",
            "quantity": 10,
            "avg_price_cents": 55.0,
            "is_paper": 1,
        }
        db.upsert_position(pos)
        positions = db.get_positions(is_paper=True)
        assert len(positions) == 1
        assert positions[0]["quantity"] == 10

        pos["quantity"] = 15
        pos["avg_price_cents"] = 57.0
        db.upsert_position(pos)
        positions = db.get_positions(is_paper=True)
        assert len(positions) == 1
        assert positions[0]["quantity"] == 15

    def test_save_fill(self, db):
        self._insert_test_market(db)
        order = {
            "order_id": "order-789",
            "ticker": "TEST-1",
            "side": "yes",
            "action": "buy",
            "price_cents": 55,
            "quantity": 5,
            "is_paper": 1,
        }
        db.save_order(order)
        fill = {
            "fill_id": "fill-001",
            "order_id": "order-789",
            "ticker": "TEST-1",
            "side": "yes",
            "action": "buy",
            "price_cents": 55,
            "quantity": 3,
            "fee_dollars": 0.01,
            "filled_at": "2026-02-20T12:00:00Z",
            "is_paper": 1,
        }
        db.save_fill(fill)
        fills = db.get_fills_today(is_paper=True)
        assert isinstance(fills, list)

    def test_bot_state(self, db):
        db.set_state("last_run", "2026-02-20T12:00:00Z")
        val = db.get_state("last_run")
        assert val == "2026-02-20T12:00:00Z"

        db.set_state("last_run", "2026-02-20T13:00:00Z")
        val = db.get_state("last_run")
        assert val == "2026-02-20T13:00:00Z"
