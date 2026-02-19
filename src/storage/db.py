"""SQLite persistence layer."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.bot.logging import get_logger

log = get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "kalshi_weather.db"


class Database:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_schema(self) -> None:
        schema_sql = _SCHEMA_PATH.read_text()
        self.conn.executescript(schema_sql)
        log.info("Database schema initialized at %s", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Forecasts ───────────────────────────────────────────

    def save_forecast(
        self,
        city_id: str,
        forecast_date: str,
        predicted_high: float | None,
        predicted_low: float | None,
        sigma: float,
        hourly_json: list | None = None,
        raw_json: dict | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO forecasts
               (city_id, fetched_at_utc, forecast_date, predicted_high,
                predicted_low, sigma, hourly_json, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                city_id,
                now,
                forecast_date,
                predicted_high,
                predicted_low,
                sigma,
                json.dumps(hourly_json) if hourly_json else None,
                json.dumps(raw_json) if raw_json else None,
            ),
        )
        self.conn.commit()

    def get_latest_forecast(self, city_id: str, forecast_date: str) -> dict | None:
        row = self.conn.execute(
            """SELECT * FROM forecasts
               WHERE city_id = ? AND forecast_date = ?
               ORDER BY fetched_at_utc DESC LIMIT 1""",
            (city_id, forecast_date),
        ).fetchone()
        return dict(row) if row else None

    # ── Markets ─────────────────────────────────────────────

    def upsert_market(self, market: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO weather_markets
               (ticker, event_ticker, city, market_date, market_type,
                strike_low, strike_high, strike_op, close_time, status, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                market["ticker"],
                market.get("event_ticker"),
                market["city"],
                market["market_date"],
                market["market_type"],
                market.get("strike_low"),
                market.get("strike_high"),
                market.get("strike_op"),
                market["close_time"],
                market.get("status", "open"),
                now,
            ),
        )
        self.conn.commit()

    def get_open_markets(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM weather_markets WHERE status = 'open' ORDER BY market_date, city"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Orders ──────────────────────────────────────────────

    def save_order(self, order: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO orders
               (order_id, ticker, side, action, price_cents, quantity,
                filled_qty, status, created_at, updated_at, is_paper,
                model_prob, model_ev)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order["order_id"],
                order["ticker"],
                order["side"],
                order["action"],
                order["price_cents"],
                order["quantity"],
                order.get("filled_qty", 0),
                order.get("status", "resting"),
                order.get("created_at", now),
                now,
                order.get("is_paper", 1),
                order.get("model_prob"),
                order.get("model_ev"),
            ),
        )
        self.conn.commit()

    def get_open_orders(self, is_paper: bool = True) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE status = 'resting' AND is_paper = ?",
            (1 if is_paper else 0,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_order_status(self, order_id: str, status: str, filled_qty: int | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if filled_qty is not None:
            self.conn.execute(
                "UPDATE orders SET status = ?, filled_qty = ?, updated_at = ? WHERE order_id = ?",
                (status, filled_qty, now, order_id),
            )
        else:
            self.conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (status, now, order_id),
            )
        self.conn.commit()

    # ── Positions ───────────────────────────────────────────

    def upsert_position(self, pos: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO positions
               (ticker, side, quantity, avg_price_cents, unrealized_pnl,
                realized_pnl, opened_at, last_updated, is_paper)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(ticker, side, is_paper) DO UPDATE SET
                 quantity = excluded.quantity,
                 avg_price_cents = excluded.avg_price_cents,
                 unrealized_pnl = excluded.unrealized_pnl,
                 realized_pnl = excluded.realized_pnl,
                 last_updated = excluded.last_updated""",
            (
                pos["ticker"],
                pos["side"],
                pos["quantity"],
                pos["avg_price_cents"],
                pos.get("unrealized_pnl", 0),
                pos.get("realized_pnl", 0),
                pos.get("opened_at", now),
                now,
                pos.get("is_paper", 1),
            ),
        )
        self.conn.commit()

    def get_positions(self, is_paper: bool = True) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE quantity > 0 AND is_paper = ?",
            (1 if is_paper else 0,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_positions(self, is_paper: bool = True) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE is_paper = ?",
            (1 if is_paper else 0,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Fills ───────────────────────────────────────────────

    def save_fill(self, fill: dict) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO fills
               (fill_id, order_id, ticker, side, action, price_cents,
                quantity, fee_dollars, filled_at, is_paper)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fill["fill_id"],
                fill["order_id"],
                fill["ticker"],
                fill["side"],
                fill["action"],
                fill["price_cents"],
                fill["quantity"],
                fill.get("fee_dollars", 0),
                fill["filled_at"],
                fill.get("is_paper", 1),
            ),
        )
        self.conn.commit()

    def get_fills_today(self, is_paper: bool = True) -> list[dict]:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT * FROM fills WHERE filled_at >= ? AND is_paper = ? ORDER BY filled_at",
            (today, 1 if is_paper else 0),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Daily P&L ───────────────────────────────────────────

    def update_daily_pnl(
        self,
        realized_pnl: float,
        fees_paid: float,
        num_trades: int,
        num_markets: int,
        is_paper: bool = True,
    ) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.conn.execute(
            """INSERT INTO daily_pnl (date_utc, realized_pnl, fees_paid, num_trades, num_markets, is_paper)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date_utc) DO UPDATE SET
                 realized_pnl = excluded.realized_pnl,
                 fees_paid = excluded.fees_paid,
                 num_trades = excluded.num_trades,
                 num_markets = excluded.num_markets""",
            (today, realized_pnl, fees_paid, num_trades, num_markets, 1 if is_paper else 0),
        )
        self.conn.commit()

    def get_daily_pnl_history(self, days: int = 30, is_paper: bool = True) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM daily_pnl WHERE is_paper = ?
               ORDER BY date_utc DESC LIMIT ?""",
            (1 if is_paper else 0, days),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Bot State ───────────────────────────────────────────

    def set_state(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        self.conn.commit()

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None
