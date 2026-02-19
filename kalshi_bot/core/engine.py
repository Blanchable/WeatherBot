"""Bot engine - orchestrates the market making loop."""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Callable

from kalshi_bot.core.api import KalshiApiClient
from kalshi_bot.core.config import BotConfig, Credentials
from kalshi_bot.core.market_data import MarketDataManager
from kalshi_bot.core.order_manager import OrderManager
from kalshi_bot.core.risk_manager import RiskManager
from kalshi_bot.strategy.market_maker import MarketMakingStrategy, Quote

logger = logging.getLogger(__name__)


class BotEngine:
    """Main bot engine that runs the market making loop."""

    def __init__(self, config: BotConfig, credentials: Credentials):
        self.config = config
        self.credentials = credentials

        self.api = KalshiApiClient(config.api, credentials)
        self.market_data = MarketDataManager()
        self.order_manager = OrderManager(self.api)
        self.risk_manager = RiskManager(config.risk, self.api)
        self.strategy = MarketMakingStrategy(config.strategy, self.market_data)

        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._active_markets: list[str] = []
        self._current_quotes: dict[str, Quote] = {}
        self._cycle_count = 0
        self._last_error: str = ""

        # Callbacks for GUI updates
        self._on_status_change: Optional[Callable] = None
        self._on_data_update: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        self.risk_manager.register_kill_switch_callback(self._on_kill_switch)

    def set_callbacks(self, on_status=None, on_data=None, on_error=None):
        self._on_status_change = on_status
        self._on_data_update = on_data
        self._on_error = on_error

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def active_markets(self) -> list[str]:
        return list(self._active_markets)

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> bool:
        if self._running:
            return True

        if not self.api.login():
            self._last_error = "Failed to authenticate with Kalshi"
            self._fire_error(self._last_error)
            return False

        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BotEngine")
        self._thread.start()
        self._fire_status("running")
        logger.info("Bot engine started")
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        self._emergency_cancel()
        self._fire_status("stopped")
        logger.info("Bot engine stopped")

    def pause(self):
        self._paused = True
        self._emergency_cancel()
        self._fire_status("paused")
        logger.info("Bot paused")

    def resume(self):
        self._paused = False
        self._fire_status("running")
        logger.info("Bot resumed")

    def emergency_stop(self):
        """Kill switch - cancel everything and stop."""
        logger.critical("EMERGENCY STOP")
        self._running = False
        self._emergency_cancel()
        self._fire_status("emergency_stopped")

    def _emergency_cancel(self):
        try:
            cancelled = self.api.cancel_all_orders()
            logger.info("Emergency cancelled %d orders", cancelled)
        except Exception as e:
            logger.error("Error during emergency cancel: %s", e)

    def _run_loop(self):
        """Main bot loop."""
        while self._running:
            try:
                if self._paused:
                    time.sleep(1)
                    continue

                cycle_start = time.time()
                self._cycle_count += 1

                # 1. Discover/refresh markets
                if self._cycle_count % 20 == 1:
                    self._discover_markets()

                # 2. Update market data
                self._update_market_data()

                # 3. Sync positions and orders
                self.risk_manager.sync_positions()
                self.order_manager.sync_orders()

                # 4. Check risk limits
                risk_ok, risk_reason = self.risk_manager.check_limits()
                if not risk_ok:
                    logger.warning("Risk limit breached: %s - cancelling all orders", risk_reason)
                    self._emergency_cancel()
                    self._fire_error(f"Risk: {risk_reason}")
                    time.sleep(5)
                    continue

                # 5. Update strategy positions
                for ticker in self._active_markets:
                    pos = self.risk_manager.get_net_position(ticker)
                    self.strategy.update_position(ticker, pos)

                # 6. Compute and place quotes
                for ticker in self._active_markets:
                    self._manage_market(ticker)

                # 7. Notify GUI
                self._fire_data_update()

                # 8. Sleep until next cycle
                elapsed = time.time() - cycle_start
                sleep_time = max(0.1, self.config.strategy.quote_refresh_seconds - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                self._last_error = str(e)
                logger.error("Bot loop error: %s", e, exc_info=True)
                self._fire_error(str(e))
                time.sleep(5)

    def _discover_markets(self):
        """Find suitable markets to trade, ranked by liquidity.

        For series with many strike levels (e.g. KXBTC with 75 buckets),
        only the most liquid near-the-money markets are selected.
        """
        candidates = []  # (score, ticker) tuples
        mc = self.config.market

        for series_ticker in mc.target_series:
            try:
                events = self.api.get_events(series_ticker=series_ticker, status="open")
                if not events:
                    events = self.api.get_events(series_ticker=series_ticker)

                for event in events[:3]:
                    event_ticker = event.get("event_ticker", "")
                    markets = event.get("markets", [])
                    if not markets:
                        markets = self.api.get_markets(event_ticker=event_ticker)

                    event_candidates = []

                    for market in markets:
                        ticker = market.get("ticker", "")
                        if not ticker:
                            continue

                        status = market.get("status", "")
                        if status not in ("open", "active", ""):
                            continue

                        self.market_data.update_market_info(ticker, market)
                        info = self.market_data.get_market_info(ticker)
                        if not info:
                            continue

                        hours_left = info.hours_to_close
                        if hours_left is not None:
                            if hours_left > mc.max_hours_to_expiry:
                                continue
                            if hours_left < mc.min_hours_to_expiry:
                                continue

                        # Price filter: skip deep OTM buckets with no action
                        yes_bid = market.get("yes_bid", 0) or 0
                        yes_ask = market.get("yes_ask", 0) or 0
                        mid = (yes_bid + yes_ask) / 2 if (yes_bid and yes_ask) else yes_ask or yes_bid
                        if mid < mc.min_price_cents or mid > mc.max_price_cents:
                            if yes_bid == 0 and yes_ask == 0:
                                continue
                            if mid > 0 and (mid < mc.min_price_cents or mid > mc.max_price_cents):
                                continue

                        # Score: prefer markets closer to 50c (near the money),
                        # with tighter spreads, and more volume
                        volume = market.get("volume", 0) or 0
                        open_interest = market.get("open_interest", 0) or 0
                        spread = (yes_ask - yes_bid) if (yes_ask and yes_bid) else 99
                        nearness = 50 - abs(50 - mid) if mid > 0 else 0

                        score = (
                            nearness * 3
                            + min(volume, 5000) / 50
                            + min(open_interest, 2000) / 40
                            - spread * 2
                        )

                        event_candidates.append((score, ticker))

                    # Per-event cap: only keep the best N from this event
                    event_candidates.sort(key=lambda x: x[0], reverse=True)
                    candidates.extend(event_candidates[:mc.max_markets_per_event])

            except Exception as e:
                logger.error("Error discovering markets for %s: %s", series_ticker, e)

        # Global ranking: pick the best markets across all series
        candidates.sort(key=lambda x: x[0], reverse=True)
        new_markets = [ticker for _, ticker in candidates[:mc.max_active_markets]]

        if new_markets:
            self._active_markets = new_markets
            logger.info(
                "Active markets (%d): %s",
                len(self._active_markets),
                [f"{t} (score={s:.0f})" for s, t in candidates[:len(new_markets)]],
            )
        elif not self._active_markets:
            logger.warning("No suitable markets found for series: %s", mc.target_series)

    def _update_market_data(self):
        """Fetch order books for active markets. Trades fetched less often."""
        for ticker in self._active_markets:
            try:
                ob_data = self.api.get_orderbook(ticker)
                if ob_data:
                    self.market_data.update_orderbook(ticker, ob_data)

                # Trades only every 4th cycle to save API calls
                if self._cycle_count % 4 == 0:
                    trades = self.api.get_trades(ticker, limit=20)
                    if trades:
                        self.market_data.add_trades(ticker, trades)

            except Exception as e:
                logger.error("Error updating data for %s: %s", ticker, e)

    def _manage_market(self, ticker: str):
        """Compute and place/update quotes for a single market."""
        quote = self.strategy.compute_quote(ticker)
        if quote is None:
            return

        if not quote.is_valid:
            if quote.reason:
                logger.debug("Skipping %s: %s", ticker, quote.reason)
            return

        # Check if requoting is needed
        current = self._current_quotes.get(ticker)
        if current and not self.strategy.should_requote(ticker, current):
            return

        # Check risk before placing
        bid_ok, _ = self.risk_manager.can_place_order(ticker, quote.bid_size, True)
        ask_ok, _ = self.risk_manager.can_place_order(ticker, quote.ask_size, False)

        if not bid_ok and not ask_ok:
            return

        # Cancel and replace
        self.order_manager.cancel_all(ticker)
        time.sleep(0.05)

        bid_order = None
        ask_order = None
        if bid_ok:
            bid_order = self.order_manager.place_bid(ticker, quote.bid_price, quote.bid_size)
        if ask_ok:
            ask_order = self.order_manager.place_ask(ticker, quote.ask_price, quote.ask_size)

        if bid_order or ask_order:
            self._current_quotes[ticker] = quote
            logger.info(
                "Quoted %s: %dc/%dc (spread=%d, fv=%.1f, skew=%.2f)",
                ticker, quote.bid_price, quote.ask_price,
                quote.spread, quote.fair_value, quote.inventory_skew,
            )

    def _on_kill_switch(self, reason: str):
        self.emergency_stop()
        self._fire_error(f"KILL SWITCH: {reason}")

    def _fire_status(self, status: str):
        if self._on_status_change:
            try:
                self._on_status_change(status)
            except Exception:
                pass

    def _fire_data_update(self):
        if self._on_data_update:
            try:
                self._on_data_update()
            except Exception:
                pass

    def _fire_error(self, error: str):
        if self._on_error:
            try:
                self._on_error(error)
            except Exception:
                pass

    def get_status_summary(self) -> dict:
        """Get a summary of current bot state for GUI."""
        positions = {}
        for ticker in self._active_markets:
            pos = self.risk_manager.get_net_position(ticker)
            quote = self._current_quotes.get(ticker)
            ob = self.market_data.get_orderbook(ticker)
            info = self.market_data.get_market_info(ticker)
            positions[ticker] = {
                "position": pos,
                "bid": quote.bid_price if quote else None,
                "ask": quote.ask_price if quote else None,
                "fair_value": round(quote.fair_value, 1) if quote else None,
                "spread": quote.spread if quote else None,
                "market_bid": ob.best_bid if ob else None,
                "market_ask": ob.best_ask if ob else None,
                "title": info.title if info else ticker,
                "hours_to_expiry": round(info.hours_to_close, 1) if info and info.hours_to_close else None,
                "volume": info.volume if info else 0,
            }

        return {
            "running": self._running,
            "paused": self._paused,
            "cycle": self._cycle_count,
            "active_markets": len(self._active_markets),
            "open_orders": self.order_manager.active_order_count,
            "balance": self.risk_manager.current_balance,
            "daily_pnl": self.risk_manager.daily_pnl_cents,
            "total_positions": self.risk_manager.get_total_position_count(),
            "kill_switch": self.risk_manager.kill_switch_triggered,
            "last_error": self._last_error,
            "positions": positions,
        }
