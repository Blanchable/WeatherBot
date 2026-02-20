"""BTC Bucket Sniper - directional trading on Kalshi hourly BTC markets.

Strategy:
1. Fetch real-time BTC price from Coinbase (updates every second)
2. Compute theoretical probability for each $250 bucket using
   a normal distribution centered on current price with BTC volatility
3. Compare theoretical price to Kalshi market price
4. Buy underpriced buckets (theoretical > market + edge threshold)
5. Sell overpriced buckets
6. As expiry approaches, probabilities concentrate on the at-the-money
   bucket -- this is where the profit comes from (time decay capture)
"""

import logging
import math
import time
import threading
from dataclasses import dataclass
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
    theoretical_prob: float  # our model's probability (0-1)
    market_bid: int  # cents
    market_ask: int  # cents
    edge_cents: float  # theoretical - market price
    action: str  # 'buy_yes', 'buy_no', or 'skip'
    size: int


def get_btc_price() -> Optional[float]:
    """Fetch current BTC/USD spot price from Coinbase."""
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
    annual_volatility: float = 0.55,
) -> float:
    """Compute probability that BTC lands in [bucket_low, bucket_high] at close.

    Uses geometric Brownian motion: log-normal distribution of future price.
    """
    if hours_to_close <= 0.001:
        # At expiry, it's either in the bucket or not
        return 1.0 if bucket_low <= current_price < bucket_high else 0.0

    # Time in years
    T = hours_to_close / (365.25 * 24)
    sigma = annual_volatility

    # Log-normal parameters
    # Under risk-neutral pricing (drift = 0 for short horizons):
    # ln(S_T/S_0) ~ N(-sigma^2*T/2, sigma^2*T)
    mu_log = math.log(current_price) - 0.5 * sigma**2 * T
    sigma_log = sigma * math.sqrt(T)

    if sigma_log < 1e-10:
        return 1.0 if bucket_low <= current_price < bucket_high else 0.0

    # P(bucket_low <= S_T < bucket_high) = Phi(ln(high)/sigma_log) - Phi(ln(low)/sigma_log)
    z_high = (math.log(bucket_high) - mu_log) / sigma_log
    z_low = (math.log(bucket_low) - mu_log) / sigma_log

    prob = norm.cdf(z_high) - norm.cdf(z_low)
    return max(0.0, min(1.0, prob))


class BtcSniperStrategy:
    """Snipes mispriced BTC buckets on Kalshi using real-time Coinbase price."""

    def __init__(self, api: KalshiApiClient, config: BotConfig):
        self.api = api
        self.config = config
        self.btc_price: Optional[float] = None
        self.btc_price_time: float = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Strategy parameters
        self.min_edge_cents = 4  # minimum mispricing to trade (cents)
        self.order_size = 3  # contracts per trade
        self.max_position_per_bucket = 10
        self.annual_vol = 0.40  # BTC annualized vol (lower for short timeframes)
        self.max_hours_to_trade = 1.0  # only trade events closing within 1 hour
        self.min_minutes_to_close = 1  # stop 1 minute before close

    def refresh_btc_price(self) -> Optional[float]:
        price = get_btc_price()
        if price:
            self.btc_price = price
            self.btc_price_time = time.time()
        return price

    def find_opportunities(self) -> list[BucketOpportunity]:
        """Scan all open BTC events for mispriced buckets."""
        if not self.refresh_btc_price():
            return []

        opportunities = []

        events = self.api.get_events(series_ticker="KXBTC", status="open")
        for event in events[:5]:
            event_ticker = event.get("event_ticker", "")
            markets = self.api.get_markets(event_ticker=event_ticker)

            if not markets:
                continue

            # Get close time from first market
            close_str = markets[0].get("close_time", "")
            if not close_str:
                continue

            from datetime import datetime, timezone
            close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            hours_to_close = (close_dt - datetime.now(timezone.utc)).total_seconds() / 3600

            if hours_to_close > self.max_hours_to_trade:
                continue
            if hours_to_close < self.min_minutes_to_close / 60:
                continue

            for market in markets:
                opp = self._evaluate_bucket(market, hours_to_close)
                if opp and opp.action != "skip":
                    opportunities.append(opp)

        # Sort by edge (best opportunities first)
        opportunities.sort(key=lambda x: abs(x.edge_cents), reverse=True)
        return opportunities

    def _evaluate_bucket(self, market: dict, hours_to_close: float) -> Optional[BucketOpportunity]:
        ticker = market.get("ticker", "")
        parts = ticker.split("-")
        if len(parts) < 3:
            return None

        strike_part = parts[2]
        if not strike_part.startswith("B"):
            return None  # skip threshold markets for now

        bucket_mid = float(strike_part[1:])
        bucket_low = bucket_mid - 125  # $250 buckets, mid is center
        bucket_high = bucket_mid + 125

        yes_bid = market.get("yes_bid", 0) or 0
        yes_ask = market.get("yes_ask", 0) or 0

        # Compute theoretical probability
        theo_prob = compute_bucket_probability(
            self.btc_price, bucket_low, bucket_high,
            hours_to_close, self.annual_vol,
        )
        theo_cents = theo_prob * 100

        action = "skip"
        edge = 0.0
        size = self.order_size

        # Buy YES if theoretical price > market ask + edge threshold
        if yes_ask > 0 and theo_cents > yes_ask + self.min_edge_cents:
            action = "buy_yes"
            edge = theo_cents - yes_ask

        # Buy NO (sell YES) if theoretical price < market bid - edge threshold
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
        """Place a trade on a mispriced bucket."""
        if opp.action == "buy_yes":
            result = self.api.place_order(
                ticker=opp.ticker,
                side="yes",
                action="buy",
                order_type="limit",
                count=opp.size,
                yes_price=opp.market_ask,
            )
            if result:
                logger.info(
                    "SNIPE BUY YES %s @%dc (theo=%.1fc, edge=%.1fc, btc=$%.0f)",
                    opp.ticker, opp.market_ask, opp.theoretical_prob * 100,
                    opp.edge_cents, self.btc_price,
                )
                return True

        elif opp.action == "buy_no":
            no_price = 100 - opp.market_bid
            result = self.api.place_order(
                ticker=opp.ticker,
                side="no",
                action="buy",
                order_type="limit",
                count=opp.size,
                no_price=no_price,
            )
            if result:
                logger.info(
                    "SNIPE BUY NO %s @%dc (theo=%.1fc, edge=%.1fc, btc=$%.0f)",
                    opp.ticker, opp.market_bid, opp.theoretical_prob * 100,
                    opp.edge_cents, self.btc_price,
                )
                return True

        return False

    def run_scan(self) -> int:
        """Run one scan cycle. Returns number of trades placed."""
        opps = self.find_opportunities()
        trades = 0

        for opp in opps[:3]:  # max 3 trades per scan
            logger.info(
                "Opportunity: %s %s theo=%.1fc mkt=%d/%d edge=%.1fc",
                opp.action, opp.ticker, opp.theoretical_prob * 100,
                opp.market_bid, opp.market_ask, opp.edge_cents,
            )
            if self.execute_opportunity(opp):
                trades += 1

        return trades
