"""Main entrypoint for the Kalshi weather bot."""

from __future__ import annotations

import argparse
import logging
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from rich.console import Console

from bot.config import BotConfig
from bot.logging import configure_logging
from execution.fills import PositionState, apply_fill
from execution.live_exchange import KalshiLiveExchange
from execution.order_manager import MakerOrderManager
from kalshi.rest import KalshiRestClient
from pricing.ev import ev_buy_yes
from risk.kill_switch import ErrorKillSwitch
from risk.limits import RiskManager
from sim.paper_exchange import BookSnapshot, PaperExchange
from storage.db import SQLiteStorage
from storage.pnl import build_pnl_report, compute_exposure
from strategy.exits import PositionView, evaluate_exit
from strategy.market_discovery import WeatherMarketMeta, discover_weather_markets
from strategy.weather_strategy import TradeCandidate, WeatherStrategy
from ui.cli_dashboard import render_dashboard
from ui.gui import WeatherBotGUI
from weather.geo import city_registry
from weather.nws_forecast import ForecastSnapshot, NWSForecastClient
from weather.nws_points import NWSPointsClient

LOGGER = logging.getLogger(__name__)


class BotRuntime:
    def __init__(
        self,
        config: BotConfig,
        mode: str,
        console: Console | None = None,
        render_dashboard_output: bool = True,
    ) -> None:
        self.config = config
        self.mode = mode
        self.console = console or Console()
        self.render_dashboard_output = render_dashboard_output
        self.running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "running": False,
            "mode": mode,
            "daily_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "gross_exposure": 0.0,
            "net_exposure": 0.0,
            "positions": [],
            "candidate_count": 0,
        }

        self.storage = SQLiteStorage(config.sqlite_path)
        self.storage.init_schema()
        self.risk = RiskManager(config)
        self.kill_switch = ErrorKillSwitch(config)
        self.strategy = WeatherStrategy(config)
        self.points_client = NWSPointsClient()
        self.forecast_client = NWSForecastClient()
        self.city_map = city_registry()

        self.positions: dict[str, PositionState] = {
            pos.ticker: pos for pos in self.storage.load_positions()
        }

        self.kalshi_client = KalshiRestClient(
            base_url=config.kalshi_rest_base,
            key_id=config.kalshi_key_id,
            private_key_path=config.kalshi_private_key_path,
        )

        if mode == "live":
            if not config.kalshi_key_id:
                raise ValueError("Live mode requested but Kalshi client not configured.")
            self.exchange = KalshiLiveExchange(self.kalshi_client)
        else:
            self.exchange = PaperExchange()

        self.order_manager = MakerOrderManager(config=config, exchange=self.exchange, db=self.storage)

    def close(self) -> None:
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.kalshi_client.close()
        self.forecast_client.close()
        self.points_client.close()
        self.storage.close()

    def update_settings(self, settings: dict[str, str]) -> None:
        with self._lock:
            if "refresh_seconds" in settings:
                self.config.refresh_seconds = int(settings["refresh_seconds"])
            if "min_ev_dollars_per_contract" in settings:
                self.config.min_ev_dollars_per_contract = float(settings["min_ev_dollars_per_contract"])
            if "max_markets" in settings:
                self.config.max_markets = int(settings["max_markets"])
            if "cities" in settings:
                self.config.cities = [item.strip().upper() for item in settings["cities"].split(",") if item.strip()]

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._state["running"] = True
        self._thread = threading.Thread(target=self.run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        with self._lock:
            self._state["running"] = False

    def _fetch_markets(self) -> list:
        try:
            return self.kalshi_client.get_markets(status="open", limit=1000)
        except Exception:
            if not self.config.kalshi_key_id and self.mode == "paper":
                LOGGER.warning("Unable to fetch markets without API credentials; running idle paper loop.")
                return []
            self.kill_switch.record_error()
            LOGGER.exception("Failed to fetch markets from Kalshi")
            return []

    def _fetch_forecasts(self, metas: list[WeatherMarketMeta]) -> dict[str, ForecastSnapshot]:
        snapshots: dict[str, ForecastSnapshot] = {}
        for city_id in sorted({meta.city_id for meta in metas}):
            city = self.city_map.get(city_id)
            if city is None:
                continue
            try:
                point = self.points_client.get_point(city.lat, city.lon)
                snapshot = self.forecast_client.fetch_forecast(city, point)
            except Exception:
                self.kill_switch.record_error()
                LOGGER.exception("Failed to fetch forecast for %s", city_id)
                continue
            snapshots[city_id] = snapshot
            self.storage.insert_forecast(snapshot)
        return snapshots

    def _refresh_books(self, metas: list[WeatherMarketMeta]) -> None:
        if not isinstance(self.exchange, PaperExchange):
            return
        for meta in metas:
            if meta.yes_bid is None or meta.yes_ask is None:
                continue
            self.exchange.update_book(
                BookSnapshot(
                    ticker=meta.ticker,
                    best_yes_bid=meta.yes_bid,
                    best_yes_ask=meta.yes_ask,
                    volume_24h=meta.volume_24h,
                )
            )

    def _apply_fills(self) -> None:
        if not isinstance(self.exchange, PaperExchange):
            return
        fills = self.exchange.step()
        for fill in fills:
            position = self.positions.get(fill.ticker) or PositionState(
                ticker=fill.ticker,
                city_id=fill.city_id,
            )
            self.positions[fill.ticker] = apply_fill(position, fill)
            self.storage.record_fill(fill)
            self.storage.upsert_position(self.positions[fill.ticker])
            if self.positions[fill.ticker].contracts == 0:
                # Keep row for realized pnl history but avoid stale active map usage.
                pass
            self.storage.update_order_status(fill.order_id, "filled")
            self.order_manager.open_orders.pop(fill.order_id, None)

    def _mark_prices(self, metas: list[WeatherMarketMeta]) -> dict[str, int]:
        if isinstance(self.exchange, PaperExchange):
            return self.exchange.mark_prices()
        mark: dict[str, int] = {}
        for meta in metas:
            if meta.yes_bid is not None and meta.yes_ask is not None:
                mark[meta.ticker] = (meta.yes_bid + meta.yes_ask) // 2
        return mark

    def _queue_exit_orders(
        self,
        *,
        metas: list[WeatherMarketMeta],
        forecasts: dict[str, ForecastSnapshot],
        mark_prices: dict[str, int],
        now: datetime,
    ) -> int:
        meta_by_ticker = {meta.ticker: meta for meta in metas}
        existing_exit_tickers = {
            order.ticker
            for order in self.order_manager.open_orders.values()
            if order.action == "sell"
        }
        placed = 0
        for pos in [p for p in self.positions.values() if p.contracts > 0]:
            if pos.ticker in existing_exit_tickers:
                continue
            meta = meta_by_ticker.get(pos.ticker)
            if meta is None:
                continue
            snapshot = forecasts.get(pos.city_id)
            if snapshot is None:
                continue
            try:
                probability_yes, _, _, _ = self.strategy.estimate_market_probability(
                    market=meta,
                    snapshot=snapshot,
                    now_utc=now,
                )
            except ValueError:
                continue

            mark = mark_prices.get(pos.ticker, pos.avg_price_cents)
            model_ev = ev_buy_yes(probability_yes=probability_yes, price_cents=mark).ev_dollars_per_contract
            exit_plan = evaluate_exit(
                PositionView(
                    ticker=pos.ticker,
                    city_id=pos.city_id,
                    contracts=pos.contracts,
                    avg_entry_price_cents=pos.avg_price_cents,
                    mark_price_cents=mark,
                    model_ev_dollars_per_contract=model_ev,
                    close_time_utc=meta.close_time_utc,
                ),
                self.config,
                now_utc=now,
            )
            if exit_plan is None:
                continue

            target = exit_plan.target_price_cents
            if meta.yes_ask is not None:
                target = max(1, meta.yes_ask - 1)
            self.order_manager.place_manual_order(
                ticker=pos.ticker,
                city_id=pos.city_id,
                side="yes",
                action="sell",
                price_cents=target,
                contracts=min(exit_plan.contracts_to_exit, pos.contracts),
            )
            placed += 1
            LOGGER.info("Queued exit order %s reason=%s", pos.ticker, exit_plan.reason)
        return placed

    def run_cycle(self) -> None:
        now = datetime.now(UTC)
        kill_state = self.kill_switch.state(now)
        if kill_state.triggered:
            LOGGER.error("Kill switch active: %s", kill_state.reason)

        raw_markets = self._fetch_markets()
        metas = discover_weather_markets(
            raw_markets,
            allowed_cities=set(self.config.cities),
            max_markets=self.config.max_markets,
            only_high_temp=True,
        )
        for meta in metas:
            self.storage.upsert_market_meta(meta)
        self._refresh_books(metas)

        forecasts = self._fetch_forecasts(metas)
        candidates: list[TradeCandidate] = self.strategy.generate_entry_candidates(
            markets=metas,
            forecasts_by_city=forecasts,
            now_utc=now,
        )

        active_positions = [pos for pos in self.positions.values() if pos.contracts > 0]
        exposure = compute_exposure(active_positions)
        mark_prices = self._mark_prices(metas)
        pnl = build_pnl_report(active_positions, mark_prices)

        self._queue_exit_orders(
            metas=metas,
            forecasts=forecasts,
            mark_prices=mark_prices,
            now=now,
        )

        daily_check = self.risk.trading_enabled_for_day(pnl.realized_dollars)
        can_trade = daily_check.allowed and not kill_state.triggered
        if not can_trade:
            LOGGER.warning("New orders disabled: %s", daily_check.reason if not daily_check.allowed else kill_state.reason)
        else:
            approved: list[TradeCandidate] = []
            for candidate in candidates:
                notional = candidate.price_cents / 100.0
                check = self.risk.can_place_order(
                    city_id=candidate.city_id,
                    ticker=candidate.ticker,
                    notional_dollars=notional,
                    exposure=exposure,
                )
                if check.allowed:
                    approved.append(candidate)
            self.order_manager.place_candidates(approved[: self.config.max_markets], exposure)

        self.order_manager.cancel_stale_orders(max_age_seconds=max(60, self.config.refresh_seconds * 3))
        self._apply_fills()

        active_positions = [pos for pos in self.positions.values() if pos.contracts > 0]
        mark_prices = self._mark_prices(metas)
        pnl = build_pnl_report(active_positions, mark_prices)
        self.storage.upsert_daily_pnl(
            realized_pnl_dollars=pnl.realized_dollars,
            unrealized_pnl_dollars=pnl.unrealized_dollars,
            fees_dollars=0.0,
            gross_exposure_dollars=pnl.gross_exposure_dollars,
            net_exposure_dollars=pnl.net_exposure_dollars,
        )

        exit_only = any(self.strategy.in_exit_only_window(meta, now) for meta in metas)
        if self.render_dashboard_output:
            self.console.clear()
            render_dashboard(
                console=self.console,
                mode=self.mode,
                exit_only=exit_only,
                candidates=candidates[:10],
                positions=active_positions,
                pnl=pnl,
            )

        with self._lock:
            self._state = {
                "running": self.running,
                "mode": self.mode,
                "daily_pnl": pnl.realized_dollars,
                "unrealized_pnl": pnl.unrealized_dollars,
                "gross_exposure": pnl.gross_exposure_dollars,
                "net_exposure": pnl.net_exposure_dollars,
                "positions": [asdict(pos) for pos in active_positions],
                "candidate_count": len(candidates),
            }

    def run_forever(self) -> None:
        while self.running:
            try:
                self.run_cycle()
            except Exception:
                LOGGER.exception("Cycle failed")
                self.kill_switch.record_error()
            time.sleep(max(5, self.config.refresh_seconds))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kalshi weather trading bot")
    parser.add_argument("--mode", choices=["paper", "live"], default=None)
    parser.add_argument("--cities", default=None, help="Comma-separated city ids (NYC,LA,CHI)")
    parser.add_argument("--max-markets", type=int, default=None)
    parser.add_argument("--refresh-seconds", type=int, default=None)
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--gui", action="store_true", help="Launch Tkinter control panel")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    config = BotConfig.from_env()

    mode = args.mode or ("live" if config.live_trading else "paper")
    if args.cities:
        config.cities = [part.strip().upper() for part in args.cities.split(",") if part.strip()]
    if args.max_markets is not None:
        config.max_markets = args.max_markets
    if args.refresh_seconds is not None:
        config.refresh_seconds = args.refresh_seconds

    configure_logging(config.log_level)
    runtime = BotRuntime(
        config=config,
        mode=mode,
        console=Console(),
        render_dashboard_output=not args.gui,
    )

    try:
        if args.gui:
            runtime.start()
            app = WeatherBotGUI(controller=runtime)
            app.mainloop()
            runtime.stop()
            return

        if args.run_once:
            runtime.run_cycle()
            return

        runtime.start()
        while runtime.running:
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted, shutting down...")
    finally:
        runtime.stop()
        runtime.close()


if __name__ == "__main__":
    main()

