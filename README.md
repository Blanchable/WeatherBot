# Kalshi Weather Bot

A disciplined, maker-first trading bot for Kalshi weather markets (temperature + precipitation). Designed for low variance and small steady gains.

## Strategy Overview

- **Maker-first**: Places resting limit orders only — never IOC/snipe
- **Weather focus**: Daily high/low temperature markets, with optional precipitation
- **NWS-powered**: Uses free National Weather Service forecasts for probability estimation
- **Fee-aware**: All trades must clear a minimum EV threshold net of Kalshi fees
- **Risk-managed**: Per-market, per-city, and global exposure limits with automatic exits

## Quick Start

### 1. Setup Wizard (Recommended)

```bash
python -m src.ui.setup_wizard
```

The wizard will:
- Check prerequisites and install dependencies
- Prompt for your Kalshi API credentials
- Configure trading parameters and risk limits
- Write your `.env` file
- Optionally launch the GUI

### 2. Manual Setup

```bash
# Install dependencies
pip install -e .

# Copy and edit configuration
cp .env.example .env
# Edit .env with your Kalshi API key and private key path

# Run paper trading (CLI)
python -m src.bot.main --mode paper

# Or launch the web GUI
python -m src.ui.gui
```

### 3. CLI Options

```bash
python -m src.bot.main --mode paper --cities NYC,LA,CHI --max-markets 8 --log-level INFO
```

| Flag | Description | Default |
|------|-------------|---------|
| `--mode` | `paper` or `live` | `paper` |
| `--cities` | Comma-separated city codes | From `.env` |
| `--max-markets` | Max simultaneous markets | `8` |
| `--log-level` | Logging level | `INFO` |

### 4. Web GUI

```bash
python -m src.ui.gui
```

Opens at `http://localhost:8080` with:
- Real-time P&L dashboard and performance chart
- Position and order management
- Live log viewer
- Settings editor
- Bot start/stop controls

## Architecture

```
src/
├── bot/           # Main loop, config, logging
├── kalshi/        # API client (auth, REST, models)
├── weather/       # NWS forecast data (points, forecast, observations, city registry)
├── pricing/       # Probability distribution, EV, fees
├── strategy/      # Market discovery, trade signals, sizing, exits
├── execution/     # Order manager, fill processing
├── risk/          # Exposure limits, kill switch
├── sim/           # Paper exchange, backtest harness
├── storage/       # SQLite persistence (DB, schema, P&L tracking)
└── ui/            # CLI dashboard, web GUI, setup wizard
```

## How It Works

1. **Market Discovery**: Scans Kalshi open markets, filters for weather-related titles, parses city/date/strike info
2. **Forecast Fetch**: Retrieves NWS hourly forecasts for each city/date combination
3. **Probability Model**: Estimates P(outcome) using Normal(predicted_high, sigma) distribution
4. **EV Calculation**: Computes expected value net of maker fees; only trades if EV exceeds threshold
5. **Order Placement**: Places maker limit orders at best_bid+1 or best_ask-1
6. **Exit Management**: Time-based, model-flip, take-profit, and stop-loss exits
7. **Risk Checks**: Enforces exposure limits, daily P&L stops, and kill switch

## Risk Controls

| Parameter | Default | Description |
|-----------|---------|-------------|
| Max Gross Exposure | $250 | Total dollar exposure across all positions |
| Max Net Exposure | $150 | Net directional exposure |
| Max Per-City | $125 | Exposure per city |
| Max Per-Market | $75 | Exposure per individual market |
| Daily Stop Loss | -$50 | Halt trading for the day |
| Daily Take Profit | +$40 | Optional daily profit target |
| Min Spread | 6 cents | Skip tight markets (fee drag) |
| Min EV | $0.02/contract | Required edge per contract |

## Supported Cities

NYC, LA, CHI, DAL, MIA, HOU, PHX, PHI, DEN, ATL, SF, SEA, BOS, DCA, MSP, STL, LAS, SAN, AUS, DET

## Paper Trading

Always paper trade first. The bot defaults to paper mode and simulates fills against live orderbook data. Paper trading:

- Fills buy orders when your bid >= current best ask
- Fills sell orders when your ask <= current best bid
- Simulates partial fills based on market volume
- Tracks full P&L, fees, and positions in SQLite

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Configuration

All settings are in `.env` — see `.env.example` for documentation of every parameter.

## Important Notes

- **No guaranteed profit** — this is a tool to help execute a systematic weather trading strategy
- **Paper trade first** — validate the model on at least 2-4 weeks of data
- **Conservative defaults** — the bot is designed to avoid large losses, not maximize gains
- **Kalshi fees matter** — the maker-only approach minimizes fee drag
- **Weather markets settle on NWS climate reports** — not real-time observations
