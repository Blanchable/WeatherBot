"""Main bot entry point — orchestrates the trading loop."""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime, timezone

import click

from src.bot.config import get_settings, reload_settings
from src.bot.logging import setup_logging, get_logger
from src.kalshi.auth import KalshiAuth
from src.kalshi.rest import KalshiClient
from src.storage.db import Database
from src.strategy.market_discovery import filter_tradeable_markets, WeatherMarketMeta
from src.strategy.weather_strategy import evaluate_market, should_exit_position, TradeSignal
from src.strategy.sizing import compute_max_new_contracts
from src.strategy.exits import is_exit_only_mode, is_no_trade_window
from src.execution.order_manager import OrderManager
from src.execution.fills import FillProcessor
from src.risk.limits import RiskLimits
from src.risk.kill_switch import KillSwitch
from src.sim.paper_exchange import PaperExchange
from src.weather.geo import get_city, CITY_REGISTRY
from src.weather.nws_forecast import get_forecast_for_city, ForecastSnapshot
from src.storage.pnl import PnLTracker

log = get_logger(__name__)


class WeatherBot:
    def __init__(self, is_paper: bool = True):
        self.settings = get_settings()
        self.is_paper = is_paper
        self.db = Database()
        self.db.init_schema()
        self.auth = KalshiAuth()
        self.client = KalshiClient(self.auth)
        self.order_manager = OrderManager(self.client, self.db, is_paper)
        self.risk = RiskLimits(self.db, is_paper)
        self.kill_switch = KillSwitch()
        self.pnl_tracker = PnLTracker(self.db, is_paper)
        self.paper_exchange = PaperExchange(self.db) if is_paper else None
        self._running = False
        self._market_cache: list[WeatherMarketMeta] = []
        self._forecast_cache: dict[str, ForecastSnapshot] = {}

    async def start(self) -> None:
        mode = "PAPER" if self.is_paper else "LIVE"
        log.info("Starting Weather Bot in %s mode", mode)
        log.info("Cities: %s", self.settings.city_list)
        log.info("Max markets: %d", self.settings.max_markets)
        self._running = True

        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self.settings.refresh_seconds)
        except asyncio.CancelledError:
            log.info("Bot cancelled")
        finally:
            await self.shutdown()

    async def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        log.info("Shutting down...")
        cancelled = await self.order_manager.cancel_all()
        log.info("Cancelled %d orders on shutdown", cancelled)
        await self.client.close()
        self.db.close()

    async def _tick(self) -> None:
        """One iteration of the main loop."""
        if self.kill_switch.is_killed:
            log.warning("Kill switch active: %s", self.kill_switch.kill_reason)
            return

        try:
            # 1. Discover markets
            await self._discover_markets()

            # 2. Fetch forecasts
            await self._update_forecasts()

            # 3. Check risk limits
            if not self.risk.is_within_limits():
                log.warning("Risk limits breached — exit-only mode")
                await self._manage_exits()
                return

            # 4. Check paper fills
            if self.paper_exchange:
                await self._check_paper_fills()

            # 5. Manage existing positions (exits)
            await self._manage_exits()

            # 6. Evaluate new trades
            await self._evaluate_new_trades()

            # 7. Sync P&L
            self._sync_pnl()

        except Exception as exc:
            self.kill_switch.record_error(str(exc))
            log.error("Tick error: %s", exc, exc_info=True)

    async def _discover_markets(self) -> None:
        try:
            raw_markets = await self.client.get_markets(status="open")
            self._market_cache = filter_tradeable_markets(raw_markets, self.settings.city_list)
            for meta in self._market_cache:
                self.db.upsert_market(meta.to_dict())
            log.info("Discovered %d tradeable weather markets", len(self._market_cache))
        except Exception as exc:
            self.kill_switch.record_error(str(exc))
            log.error("Market discovery failed: %s", exc)

    async def _update_forecasts(self) -> None:
        cities_needed = set()
        dates_needed: dict[str, set[str]] = {}
        for meta in self._market_cache:
            cities_needed.add(meta.city)
            dates_needed.setdefault(meta.city, set()).add(meta.market_date)

        for city_code in cities_needed:
            city = get_city(city_code)
            if not city:
                continue
            for target_date in dates_needed.get(city_code, set()):
                cache_key = f"{city_code}_{target_date}"
                existing = self._forecast_cache.get(cache_key)
                if existing and not existing.is_stale:
                    continue
                try:
                    snapshot = await get_forecast_for_city(city, target_date)
                    if snapshot:
                        self._forecast_cache[cache_key] = snapshot
                        self.db.save_forecast(
                            city_id=city_code,
                            forecast_date=target_date,
                            predicted_high=snapshot.predicted_high,
                            predicted_low=snapshot.predicted_low,
                            sigma=get_settings().sigma_same_day,
                            hourly_json=snapshot.raw_periods,
                        )
                except Exception as exc:
                    log.error("Forecast fetch failed for %s: %s", city_code, exc)

    async def _check_paper_fills(self) -> None:
        if not self.paper_exchange:
            return
        snapshots: dict[str, dict] = {}
        for meta in self._market_cache:
            try:
                market = await self.client.get_market(meta.ticker)
                snapshots[meta.ticker] = {
                    "yes_bid": market.yes_bid,
                    "yes_ask": market.yes_ask,
                    "volume": market.volume_24h,
                }
            except Exception:
                pass

        fills = self.paper_exchange.check_fills(snapshots)
        if fills:
            log.info("Paper fills: %d", len(fills))

    async def _manage_exits(self) -> None:
        positions = self.db.get_positions(self.is_paper)
        for pos in positions:
            ticker = pos["ticker"]
            mkt_row = self.db.conn.execute(
                "SELECT * FROM weather_markets WHERE ticker = ?", (ticker,)
            ).fetchone()
            if not mkt_row:
                continue
            mkt = dict(mkt_row)
            meta = WeatherMarketMeta(
                ticker=mkt["ticker"],
                event_ticker=mkt.get("event_ticker", ""),
                city=mkt["city"],
                market_date=mkt["market_date"],
                market_type=mkt["market_type"],
                strike_low=mkt.get("strike_low"),
                strike_high=mkt.get("strike_high"),
                strike_op=mkt.get("strike_op", "range"),
                close_time=mkt["close_time"],
                title="",
            )

            cache_key = f"{meta.city}_{meta.market_date}"
            forecast = self._forecast_cache.get(cache_key)
            if not forecast:
                continue

            try:
                market = await self.client.get_market(ticker)
                current_mid = market.mid_price
            except Exception:
                continue

            exit_info = should_exit_position(
                meta=meta,
                forecast=forecast,
                position_side=pos["side"],
                avg_price_cents=pos["avg_price_cents"],
                current_mid=current_mid,
                quantity=pos["quantity"],
            )

            if exit_info:
                log.info(
                    "EXIT signal for %s: %s (pnl=%.1fc, qty=%d)",
                    ticker, exit_info["reason"], exit_info["pnl_cents"],
                    exit_info["exit_quantity"],
                )
                exit_signal = TradeSignal(
                    meta=meta,
                    side=pos["side"],
                    action="sell",
                    price_cents=int(current_mid) + (1 if pos["side"] == "yes" else -1),
                    quantity=exit_info["exit_quantity"],
                    model_prob=exit_info["current_prob"],
                    model_ev=0,
                    forecast_high=forecast.predicted_high or 0,
                    sigma=0,
                )
                await self.order_manager.place_signal(exit_signal)

    async def _evaluate_new_trades(self) -> None:
        for meta in self._market_cache:
            if is_no_trade_window(meta):
                continue
            if is_exit_only_mode(meta):
                continue

            cache_key = f"{meta.city}_{meta.market_date}"
            forecast = self._forecast_cache.get(cache_key)
            if not forecast:
                continue

            now = datetime.now(timezone.utc)
            staleness_minutes = (now - forecast.fetched_at_utc).total_seconds() / 60.0
            days_ahead = 0
            try:
                target = datetime.strptime(meta.market_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days_ahead = (target.date() - now.date()).days
            except ValueError:
                pass

            if days_ahead <= 0 and staleness_minutes > self.settings.forecast_stale_minutes_same_day:
                log.debug("Skipping %s: stale forecast (%.0fm)", meta.ticker, staleness_minutes)
                continue
            if days_ahead == 1 and staleness_minutes > self.settings.forecast_stale_minutes_next_day:
                continue

            try:
                market = await self.client.get_market(meta.ticker)
            except Exception:
                continue

            signal = evaluate_market(
                meta=meta,
                forecast=forecast,
                yes_bid=market.yes_bid,
                yes_ask=market.yes_ask,
            )

            if signal is None:
                continue

            max_qty = compute_max_new_contracts(
                ticker=meta.ticker,
                city=meta.city,
                price_cents=signal.price_cents,
                db=self.db,
                is_paper=self.is_paper,
            )

            if max_qty <= 0:
                continue

            signal.quantity = min(signal.quantity, max_qty)
            await self.order_manager.place_signal(signal)

    def _sync_pnl(self) -> None:
        mark_prices: dict[str, float] = {}
        for meta in self._market_cache:
            # Use cached or default
            mark_prices[meta.ticker] = 50.0
        self.pnl_tracker.sync_daily(mark_prices)

    def get_status(self) -> dict:
        """Return current bot status for the UI."""
        exposure = self.risk.exposure_summary()
        pnl = self.pnl_tracker.sync_daily()
        return {
            "mode": "paper" if self.is_paper else "live",
            "running": self._running,
            "kill_switch": self.kill_switch.is_killed,
            "kill_reason": self.kill_switch.kill_reason,
            "markets_tracked": len(self._market_cache),
            "active_orders": self.order_manager.active_order_count,
            **exposure,
            **pnl,
        }


async def run_bot(is_paper: bool = True) -> None:
    bot = WeatherBot(is_paper=is_paper)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))

    await bot.start()


@click.command()
@click.option("--mode", type=click.Choice(["paper", "live"]), default="paper")
@click.option("--cities", default=None, help="Comma-separated city codes")
@click.option("--max-markets", default=None, type=int)
@click.option("--log-level", default="INFO")
def cli(mode: str, cities: str | None, max_markets: int | None, log_level: str) -> None:
    setup_logging(log_level)

    if cities:
        import os
        os.environ["CITIES"] = cities
        reload_settings()
    if max_markets:
        import os
        os.environ["MAX_MARKETS"] = str(max_markets)
        reload_settings()

    is_paper = mode == "paper"
    asyncio.run(run_bot(is_paper=is_paper))


if __name__ == "__main__":
    cli()
