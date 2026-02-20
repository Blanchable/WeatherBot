"""BTC Bucket Sniper - directional trading on Kalshi hourly BTC markets.

Strategy:
1. Fetch real-time BTC price from Coinbase
2. Calibrate implied volatility from the market's own pricing
3. Find buckets where our model disagrees with the market by > threshold
4. Place ONE trade per bucket per event, then track the position
5. Profit from time decay as the ATM bucket converges to 100c at close
"""

import logging
import math
import time
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests
import numpy as np
from scipy.stats import norm  # type: ignore

from kalshi_bot.core.api import KalshiApiClient
from kalshi_bot.core.config import BotConfig

logger = logging.getLogger(__name__)

COINBASE_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"


@dataclass
class BucketOpportunity:
    ticker: str
    strike_low: float
    strike_high: float
    theoretical_prob: float
    market_bid: int
    market_ask: int
    edge_cents: float
    action: str  # 'buy_yes', 'buy_no', or 'skip'
    size: int


def get_btc_price() -> Optional[float]:
    try:
        resp = requests.get(COINBASE_URL, timeout=5)
        if resp.status_code == 200:
            return float(resp.json()["data"]["amount"])
    except Exception as e:
        logger.error("Failed to fetch BTC price: %s", e)
    return None


def compute_bucket_probability(
    current_price: float,
    bucket_low: float,
    bucket_high: float,
    hours_to_close: float,
    annual_volatility: float = 0.40,
) -> float:
    """Probability that BTC lands in [bucket_low, bucket_high] at close."""
    if hours_to_close <= 0.001:
        return 1.0 if bucket_low <= current_price < bucket_high else 0.0

    T = hours_to_close / (365.25 * 24)
    sigma = annual_volatility

    mu_log = math.log(current_price) - 0.5 * sigma**2 * T
    sigma_log = sigma * math.sqrt(T)

    if sigma_log < 1e-10:
        return 1.0 if bucket_low <= current_price < bucket_high else 0.0

    z_high = (math.log(bucket_high) - mu_log) / sigma_log
    z_low = (math.log(bucket_low) - mu_log) / sigma_log

    return max(0.0, min(1.0, norm.cdf(z_high) - norm.cdf(z_low)))


def calibrate_implied_vol(
    current_price: float,
    hours_to_close: float,
    atm_market_price_cents: int,
    bucket_width: float = 250.0,
) -> float:
    """Back out implied volatility from the ATM bucket's market price.

    If the market prices the ATM bucket at 60c, what annualized vol
    produces a 60% probability for a $250 bucket? This is much more
    reliable than guessing a fixed vol.
    """
    if atm_market_price_cents <= 1 or atm_market_price_cents >= 99:
        return 0.40
    if hours_to_close <= 0.01:
        return 0.40

    target_prob = atm_market_price_cents / 100.0
    bucket_low = current_price - bucket_width / 2
    bucket_high = current_price + bucket_width / 2

    # Binary search for volatility
    lo, hi = 0.05, 2.0
    for _ in range(30):
        mid = (lo + hi) / 2
        prob = compute_bucket_probability(current_price, bucket_low, bucket_high, hours_to_close, mid)
        if prob < target_prob:
            hi = mid
        else:
            lo = mid

    implied = (lo + hi) / 2
    logger.debug("Calibrated implied vol: %.1f%% (ATM=%dc, hrs=%.2f)", implied * 100, atm_market_price_cents, hours_to_close)
    return implied


class BtcSniperStrategy:
    """Snipes mispriced BTC buckets using real-time price + calibrated vol."""

    def __init__(self, api: KalshiApiClient, config: BotConfig):
        self.api = api
        self.config = config
        self.btc_price: Optional[float] = None
        self.btc_price_time: float = 0

        # Strategy parameters
        self.min_edge_cents = 6  # minimum mispricing to act on
        self.order_size = 3
        self.max_position_per_bucket = 3  # only ONE trade per bucket
        self.max_hours_to_trade = 0.75  # only trade events closing within 45 min
        self.min_minutes_to_close = 2

        # Position tracking: never trade the same bucket twice in one event
        self._traded_buckets: dict[str, int] = {}  # ticker -> contracts held
        self._last_event_ticker: str = ""

    def refresh_btc_price(self) -> Optional[float]:
        price = get_btc_price()
        if price:
            self.btc_price = price
            self.btc_price_time = time.time()
        return price

    def find_opportunities(self) -> list[BucketOpportunity]:
        if not self.refresh_btc_price():
            return []

        opportunities = []

        events = self.api.get_events(series_ticker="KXBTC", status="open")
        for event in events[:3]:
            event_ticker = event.get("event_ticker", "")
            markets = self.api.get_markets(event_ticker=event_ticker)

            if not markets:
                continue

            close_str = markets[0].get("close_time", "")
            if not close_str:
                continue

            close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            hours_to_close = (close_dt - datetime.now(timezone.utc)).total_seconds() / 3600

            if hours_to_close > self.max_hours_to_trade:
                continue
            if hours_to_close < self.min_minutes_to_close / 60:
                continue

            # Reset tracked buckets when event changes
            if event_ticker != self._last_event_ticker:
                self._traded_buckets.clear()
                self._last_event_ticker = event_ticker

            # Find the ATM bucket to calibrate implied vol
            implied_vol = self._calibrate_from_market(markets, hours_to_close)

            for market in markets:
                opp = self._evaluate_bucket(market, hours_to_close, implied_vol)
                if opp and opp.action != "skip":
                    opportunities.append(opp)

        opportunities.sort(key=lambda x: abs(x.edge_cents), reverse=True)
        return opportunities

    def _calibrate_from_market(self, markets: list[dict], hours_to_close: float) -> float:
        """Find the ATM bucket and calibrate implied vol from its price."""
        best_bucket = None
        best_dist = float("inf")

        for m in markets:
            ticker = m.get("ticker", "")
            parts = ticker.split("-")
            if len(parts) < 3 or not parts[2].startswith("B"):
                continue

            strike = float(parts[2][1:])
            dist = abs(strike - self.btc_price)
            yb = m.get("yes_bid", 0) or 0
            ya = m.get("yes_ask", 0) or 0

            if dist < best_dist and yb > 0 and ya > 0:
                best_dist = dist
                best_bucket = m

        if best_bucket:
            yb = best_bucket.get("yes_bid", 0) or 0
            ya = best_bucket.get("yes_ask", 0) or 0
            atm_mid = (yb + ya) // 2
            implied = calibrate_implied_vol(self.btc_price, hours_to_close, atm_mid)
            return implied

        return 0.40

    def _evaluate_bucket(self, market: dict, hours_to_close: float, implied_vol: float) -> Optional[BucketOpportunity]:
        ticker = market.get("ticker", "")
        parts = ticker.split("-")
        if len(parts) < 3 or not parts[2].startswith("B"):
            return None

        # Skip if already traded this bucket
        existing = self._traded_buckets.get(ticker, 0)
        if existing >= self.max_position_per_bucket:
            return None

        bucket_mid = float(parts[2][1:])
        bucket_low = bucket_mid - 125
        bucket_high = bucket_mid + 125

        yes_bid = market.get("yes_bid", 0) or 0
        yes_ask = market.get("yes_ask", 0) or 0

        theo_prob = compute_bucket_probability(
            self.btc_price, bucket_low, bucket_high,
            hours_to_close, implied_vol,
        )
        theo_cents = theo_prob * 100

        action = "skip"
        edge = 0.0
        size = self.order_size

        if yes_ask > 0 and theo_cents > yes_ask + self.min_edge_cents:
            action = "buy_yes"
            edge = theo_cents - yes_ask
        elif yes_bid > 0 and theo_cents < yes_bid - self.min_edge_cents:
            action = "buy_no"
            edge = yes_bid - theo_cents

        return BucketOpportunity(
            ticker=ticker,
            strike_low=bucket_low,
            strike_high=bucket_high,
            theoretical_prob=theo_prob,
            market_bid=yes_bid,
            market_ask=yes_ask,
            edge_cents=edge,
            action=action,
            size=size,
        )

    def execute_opportunity(self, opp: BucketOpportunity) -> bool:
        if opp.action == "buy_yes":
            result = self.api.place_order(
                ticker=opp.ticker, side="yes", action="buy",
                order_type="limit", count=opp.size, yes_price=opp.market_ask,
            )
            if result:
                self._traded_buckets[opp.ticker] = self._traded_buckets.get(opp.ticker, 0) + opp.size
                logger.info(
                    "SNIPE BUY YES %s @%dc (theo=%.1fc, edge=%.1fc, btc=$%.0f, pos=%d)",
                    opp.ticker, opp.market_ask, opp.theoretical_prob * 100,
                    opp.edge_cents, self.btc_price, self._traded_buckets[opp.ticker],
                )
                return True

        elif opp.action == "buy_no":
            no_price = 100 - opp.market_bid
            result = self.api.place_order(
                ticker=opp.ticker, side="no", action="buy",
                order_type="limit", count=opp.size, no_price=no_price,
            )
            if result:
                self._traded_buckets[opp.ticker] = self._traded_buckets.get(opp.ticker, 0) + opp.size
                logger.info(
                    "SNIPE BUY NO %s @%dc (theo=%.1fc, edge=%.1fc, btc=$%.0f, pos=%d)",
                    opp.ticker, opp.market_bid, opp.theoretical_prob * 100,
                    opp.edge_cents, self.btc_price, self._traded_buckets[opp.ticker],
                )
                return True

        return False

    def run_scan(self) -> int:
        opps = self.find_opportunities()
        trades = 0
        for opp in opps[:2]:  # max 2 trades per scan
            logger.info(
                "Opportunity: %s %s theo=%.1fc mkt=%d/%d edge=%.1fc",
                opp.action, opp.ticker, opp.theoretical_prob * 100,
                opp.market_bid, opp.market_ask, opp.edge_cents,
            )
            if self.execute_opportunity(opp):
                trades += 1
        return trades
