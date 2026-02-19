# Kalshi Weather Bot (Maker-First, Low-Variance)

Conservative weather-market trading bot for Kalshi with:

- **maker-first execution**
- **strict no-trade filters**
- **bounded inventory + forced exits**
- **NWS-based probability model**
- **paper trading and live modes**
- **SQLite persistence**
- **Rich CLI dashboard + Tkinter GUI**

> This project is built to reduce variance and fee drag, not to guarantee profits.

## Features

- Weather market discovery via title parsing + city whitelist fallback
- NWS forecast ingestion (`points`, hourly/daily forecast, optional observations)
- Normal-distribution pricing for temperature ranges / thresholds
- EV checks net of fee estimates and cent-rounding
- Maker-only order manager with slow cancel/replace cadence
- Risk limits:
  - per-market, per-city, gross/net caps
  - daily stop-loss / take-profit halts
  - API error-rate kill switch
- Forced exits policy logic (time, model flip, TP/SL)
- SQLite storage for forecasts, market metadata, orders, fills, positions, daily PnL
- Paper exchange simulator with top-of-book fill logic
- Required tests for parser, fees, and probability modules

## Project Layout

```text
src/
  bot/
  kalshi/
  weather/
  pricing/
  strategy/
  execution/
  risk/
  storage/
  sim/
  ui/
tests/
```

## Setup

### Option A (recommended): `uv`

```bash
uv sync --extra dev
cp .env.example .env
```

### Option B: pip

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
```

### Windows setup wizard

Run:

```bat
setup_wizard.bat
```

This initializes a virtual environment, installs dependencies, creates `.env`, and then launches the paper-trading GUI automatically.

## Configure Environment

Edit `.env`:

- Kalshi API base URL (`KALSHI_REST_BASE`)
- credentials (`KALSHI_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`) for live trading
- city universe and risk controls

Default mode is conservative paper trading.

## Running

### Paper mode (recommended first)

```bash
python -m bot.main --mode paper
```

### Live mode

```bash
python -m bot.main --mode live
```

### Useful flags

```bash
python -m bot.main --mode paper --cities NYC,LA,CHI --max-markets 8 --refresh-seconds 20
python -m bot.main --mode paper --run-once
python -m bot.main --mode paper --gui
```

## GUI

Tkinter GUI includes:

- Start / stop controls
- Editable settings (refresh, min EV, max markets, cities)
- Live summary (PnL + exposure)
- Position table

Launch:

```bash
python -m bot.main --mode paper --gui
```

## Testing

```bash
pytest
```

Tests include:

- `tests/test_market_parser.py`
- `tests/test_fees.py`
- `tests/test_distribution.py`

## Notes / Scope

- REST polling is primary; websocket module is included as a future extension.
- Live adapter currently supports YES-side limit orders.
- Fee formulas are approximations and should be validated against Kalshi’s latest schedule.
- This is not investment advice.