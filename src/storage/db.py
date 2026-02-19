"""SQLite persistence layer."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from execution.fills import FillEvent, PositionState
from strategy.market_discovery import WeatherMarketMeta
from weather.nws_forecast import ForecastSnapshot


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init_schema(self, schema_path: str | Path | None = None) -> None:
        if schema_path is None:
            schema_path = Path(__file__).with_name("schema.sql")
        sql = Path(schema_path).read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    def insert_forecast(self, snapshot: ForecastSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO forecast_snapshots (
                city_id, fetched_at_utc, forecast_valid_from_utc, confidence_spread_f, raw_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                snapshot.city_id,
                snapshot.fetched_at_utc.isoformat(),
                snapshot.forecast_valid_from.isoformat(),
                snapshot.confidence_spread_f,
                snapshot.raw_json,
            ),
        )
        self.conn.commit()

    def latest_forecast_json(self, city_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT raw_json FROM forecast_snapshots
            WHERE city_id = ?
            ORDER BY fetched_at_utc DESC
            LIMIT 1
            """,
            (city_id,),
        ).fetchone()
        return None if row is None else str(row["raw_json"])

    def upsert_market_meta(self, meta: WeatherMarketMeta) -> None:
        self.conn.execute(
            """
            INSERT INTO market_meta (
                ticker, city_id, market_type, target_date, strike_type, strike_low,
                strike_high, close_time_utc, title, subtitle, volume_24h, open_interest,
                yes_bid, yes_ask, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                city_id = excluded.city_id,
                market_type = excluded.market_type,
                target_date = excluded.target_date,
                strike_type = excluded.strike_type,
                strike_low = excluded.strike_low,
                strike_high = excluded.strike_high,
                close_time_utc = excluded.close_time_utc,
                title = excluded.title,
                subtitle = excluded.subtitle,
                volume_24h = excluded.volume_24h,
                open_interest = excluded.open_interest,
                yes_bid = excluded.yes_bid,
                yes_ask = excluded.yes_ask,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                meta.ticker,
                meta.city_id,
                meta.market_type,
                meta.target_date.isoformat(),
                meta.strike.strike_type,
                meta.strike.low,
                meta.strike.high,
                meta.close_time_utc.isoformat(),
                meta.title,
                meta.subtitle,
                meta.volume_24h,
                meta.open_interest,
                meta.yes_bid,
                meta.yes_ask,
                _utc_now_iso(),
            ),
        )
        self.conn.commit()

    def record_order(
        self,
        *,
        order_id: str,
        ticker: str,
        city_id: str,
        side: str,
        action: str,
        price_cents: int,
        contracts: int,
        status: str,
    ) -> None:
        now = _utc_now_iso()
        self.conn.execute(
            """
            INSERT OR REPLACE INTO orders (
                order_id, ticker, city_id, side, action, price_cents, contracts, status,
                created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, ticker, city_id, side, action, price_cents, contracts, status, now, now),
        )
        self.conn.commit()

    def update_order_status(self, order_id: str, status: str) -> None:
        self.conn.execute(
            """
            UPDATE orders
            SET status = ?, updated_at_utc = ?
            WHERE order_id = ?
            """,
            (status, _utc_now_iso(), order_id),
        )
        self.conn.commit()

    def record_fill(self, fill: FillEvent) -> None:
        self.conn.execute(
            """
            INSERT INTO fills (
                order_id, ticker, city_id, side, action, price_cents, contracts, mode, filled_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill.order_id,
                fill.ticker,
                fill.city_id,
                fill.side,
                fill.action,
                fill.price_cents,
                fill.contracts,
                fill.mode,
                fill.filled_at_utc.isoformat(),
            ),
        )
        self.conn.commit()

    def upsert_position(self, position: PositionState) -> None:
        self.conn.execute(
            """
            INSERT INTO positions (ticker, city_id, contracts, avg_price_cents, realized_pnl_dollars, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                city_id = excluded.city_id,
                contracts = excluded.contracts,
                avg_price_cents = excluded.avg_price_cents,
                realized_pnl_dollars = excluded.realized_pnl_dollars,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                position.ticker,
                position.city_id,
                position.contracts,
                position.avg_price_cents,
                position.realized_pnl_dollars,
                _utc_now_iso(),
            ),
        )
        self.conn.commit()

    def load_positions(self) -> list[PositionState]:
        rows = self.conn.execute("SELECT * FROM positions").fetchall()
        return [
            PositionState(
                ticker=row["ticker"],
                city_id=row["city_id"],
                contracts=int(row["contracts"]),
                avg_price_cents=int(row["avg_price_cents"]),
                realized_pnl_dollars=float(row["realized_pnl_dollars"]),
            )
            for row in rows
        ]

    def get_daily_realized_pnl(self, trading_day: date | None = None) -> float:
        day = (trading_day or datetime.now(UTC).date()).isoformat()
        row = self.conn.execute(
            "SELECT realized_pnl_dollars FROM pnl_daily WHERE trading_day = ?",
            (day,),
        ).fetchone()
        if row is None:
            return 0.0
        return float(row["realized_pnl_dollars"])

    def upsert_daily_pnl(
        self,
        *,
        realized_pnl_dollars: float,
        unrealized_pnl_dollars: float,
        fees_dollars: float,
        gross_exposure_dollars: float,
        net_exposure_dollars: float,
        trading_day: date | None = None,
    ) -> None:
        day = (trading_day or datetime.now(UTC).date()).isoformat()
        self.conn.execute(
            """
            INSERT INTO pnl_daily (
                trading_day, realized_pnl_dollars, unrealized_pnl_dollars, fees_dollars,
                gross_exposure_dollars, net_exposure_dollars, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trading_day) DO UPDATE SET
                realized_pnl_dollars = excluded.realized_pnl_dollars,
                unrealized_pnl_dollars = excluded.unrealized_pnl_dollars,
                fees_dollars = excluded.fees_dollars,
                gross_exposure_dollars = excluded.gross_exposure_dollars,
                net_exposure_dollars = excluded.net_exposure_dollars,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                day,
                realized_pnl_dollars,
                unrealized_pnl_dollars,
                fees_dollars,
                gross_exposure_dollars,
                net_exposure_dollars,
                _utc_now_iso(),
            ),
        )
        self.conn.commit()

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE status = 'open' ORDER BY created_at_utc DESC"
        ).fetchall()
        return [dict(row) for row in rows]

