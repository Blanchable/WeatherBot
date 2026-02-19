"""Conservative risk limits and eligibility checks."""

from __future__ import annotations

from dataclasses import dataclass

from bot.config import BotConfig
from strategy.sizing import ExposureSnapshot


@dataclass(slots=True)
class RiskCheck:
    allowed: bool
    reason: str


class RiskManager:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def trading_enabled_for_day(self, daily_pnl: float) -> RiskCheck:
        if daily_pnl <= -abs(self.config.daily_stop_loss_dollars):
            return RiskCheck(False, "daily_stop_loss_hit")
        if daily_pnl >= abs(self.config.daily_take_profit_dollars):
            return RiskCheck(False, "daily_take_profit_hit")
        return RiskCheck(True, "ok")

    def can_place_order(
        self,
        *,
        city_id: str,
        ticker: str,
        notional_dollars: float,
        exposure: ExposureSnapshot,
    ) -> RiskCheck:
        if notional_dollars <= 0:
            return RiskCheck(False, "non_positive_notional")
        if exposure.gross_dollars + notional_dollars > self.config.max_gross_exposure_dollars:
            return RiskCheck(False, "max_gross_exposure")
        if abs(exposure.net_dollars + notional_dollars) > self.config.max_net_exposure_dollars:
            return RiskCheck(False, "max_net_exposure")
        city_used = exposure.city_exposure.get(city_id, 0.0)
        if city_used + notional_dollars > self.config.max_exposure_per_city_dollars:
            return RiskCheck(False, "max_city_exposure")
        market_used = exposure.market_exposure.get(ticker, 0.0)
        if market_used + notional_dollars > self.config.max_exposure_per_market_dollars:
            return RiskCheck(False, "max_market_exposure")
        return RiskCheck(True, "ok")

