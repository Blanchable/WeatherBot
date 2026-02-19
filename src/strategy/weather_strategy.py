"""Core weather strategy: selection, pricing and entry candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bot.config import BotConfig
from pricing.distribution import fair_price_cents, predicted_daily_high, probability_for_strike
from pricing.ev import EVResult, ev_buy_yes
from strategy.market_discovery import WeatherMarketMeta
from weather.nws_forecast import ForecastSnapshot


@dataclass(slots=True)
class TradeCandidate:
    ticker: str
    city_id: str
    side: str
    action: str
    price_cents: int
    contracts: int
    probability_yes: float
    fair_price_cents: int
    ev_dollars_per_contract: float
    spread_cents: int
    model_mean_high_f: float
    model_sigma_f: float
    reason: str


class WeatherStrategy:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def _is_forecast_stale(self, market: WeatherMarketMeta, snapshot: ForecastSnapshot, now_utc: datetime) -> bool:
        days_out = (market.target_date - now_utc.date()).days
        age = snapshot.age_minutes(now_utc)
        if days_out <= 0:
            return age > self.config.forecast_stale_minutes_same_day
        return age > self.config.forecast_stale_minutes_next_day

    def _in_no_trade_window(self, market: WeatherMarketMeta, now_utc: datetime) -> bool:
        seconds_to_close = (market.close_time_utc - now_utc).total_seconds()
        return seconds_to_close <= self.config.no_trade_window_seconds

    def in_exit_only_window(self, market: WeatherMarketMeta, now_utc: datetime) -> bool:
        seconds_to_close = (market.close_time_utc - now_utc).total_seconds()
        return seconds_to_close <= self.config.exit_only_window_seconds

    def _evaluate_entry(
        self,
        market: WeatherMarketMeta,
        snapshot: ForecastSnapshot,
        now_utc: datetime,
    ) -> TradeCandidate | None:
        if self._is_forecast_stale(market, snapshot, now_utc):
            return None
        if self._in_no_trade_window(market, now_utc):
            return None
        if market.volume_24h < self.config.min_24h_volume:
            return None

        spread = market.spread_cents
        if spread is None or spread < self.config.min_spread_cents:
            return None
        if market.yes_bid is None:
            return None

        probability_yes, fair, mean_high, sigma = self.estimate_market_probability(
            market=market,
            snapshot=snapshot,
            now_utc=now_utc,
        )

        quote_price = min(99, market.yes_bid + 1)
        if market.yes_ask is not None and quote_price >= market.yes_ask:
            quote_price = max(1, market.yes_bid)

        if quote_price > fair - self.config.edge_buffer_cents:
            return None

        ev_result: EVResult = ev_buy_yes(
            probability_yes=probability_yes,
            price_cents=quote_price,
            maker=self.config.maker_only,
        )
        if ev_result.ev_dollars_per_contract < self.config.min_ev_dollars_per_contract:
            return None

        # Tail prices are often selection traps; require extra edge and liquidity.
        if quote_price <= 5 or quote_price >= 95:
            if ev_result.ev_dollars_per_contract < 2 * self.config.min_ev_dollars_per_contract:
                return None
            if market.volume_24h < 2 * self.config.min_24h_volume:
                return None

        return TradeCandidate(
            ticker=market.ticker,
            city_id=market.city_id,
            side="yes",
            action="buy",
            price_cents=quote_price,
            contracts=1,
            probability_yes=probability_yes,
            fair_price_cents=fair,
            ev_dollars_per_contract=ev_result.ev_dollars_per_contract,
            spread_cents=spread,
            model_mean_high_f=mean_high,
            model_sigma_f=sigma,
            reason="maker_entry_ev_positive",
        )

    def estimate_market_probability(
        self,
        *,
        market: WeatherMarketMeta,
        snapshot: ForecastSnapshot,
        now_utc: datetime,
    ) -> tuple[float, int, float, float]:
        mean_high = predicted_daily_high(
            hourly_times=snapshot.hourly_times_utc,
            hourly_temps_f=snapshot.hourly_temps_f,
            target_date=market.target_date,
        )
        days_out = max(0, (market.target_date - now_utc.date()).days)
        sigma = self.config.horizon_sigma(days_out=days_out)
        probability_yes = probability_for_strike(mean_high, sigma, market.strike)
        fair = fair_price_cents(probability_yes)
        return probability_yes, fair, mean_high, sigma

    def generate_entry_candidates(
        self,
        markets: list[WeatherMarketMeta],
        forecasts_by_city: dict[str, ForecastSnapshot],
        now_utc: datetime | None = None,
    ) -> list[TradeCandidate]:
        now = now_utc or datetime.now(UTC)
        candidates: list[TradeCandidate] = []
        for market in markets:
            snapshot = forecasts_by_city.get(market.city_id)
            if snapshot is None:
                continue
            try:
                candidate = self._evaluate_entry(market, snapshot, now_utc=now)
            except ValueError:
                continue
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda item: item.ev_dollars_per_contract, reverse=True)
        return candidates

