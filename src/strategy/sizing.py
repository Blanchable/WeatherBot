"""Position sizing constrained by conservative exposure caps."""

from __future__ import annotations

from dataclasses import dataclass, field

from bot.config import BotConfig
from strategy.weather_strategy import TradeCandidate


@dataclass(slots=True)
class ExposureSnapshot:
    gross_dollars: float = 0.0
    net_dollars: float = 0.0
    city_exposure: dict[str, float] = field(default_factory=dict)
    market_exposure: dict[str, float] = field(default_factory=dict)


def _safe_contract_cap(remaining_dollars: float, contract_notional: float) -> int:
    if contract_notional <= 0:
        return 0
    if remaining_dollars <= 0:
        return 0
    return int(remaining_dollars // contract_notional)


def recommend_contracts(
    candidate: TradeCandidate,
    exposure: ExposureSnapshot,
    config: BotConfig,
) -> int:
    desired = max(1, min(candidate.contracts, config.max_order_size_contracts))
    contract_notional = candidate.price_cents / 100.0
    if contract_notional <= 0:
        return 0

    gross_remaining = config.max_gross_exposure_dollars - exposure.gross_dollars
    net_remaining = config.max_net_exposure_dollars - abs(exposure.net_dollars)
    city_remaining = config.max_exposure_per_city_dollars - exposure.city_exposure.get(candidate.city_id, 0.0)
    market_remaining = config.max_exposure_per_market_dollars - exposure.market_exposure.get(candidate.ticker, 0.0)

    max_by_constraints = min(
        _safe_contract_cap(gross_remaining, contract_notional),
        _safe_contract_cap(net_remaining, contract_notional),
        _safe_contract_cap(city_remaining, contract_notional),
        _safe_contract_cap(market_remaining, contract_notional),
        config.max_order_size_contracts,
    )
    return max(0, min(desired, max_by_constraints))

