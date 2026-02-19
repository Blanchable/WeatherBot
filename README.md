# Kalshi Market Making Bot

An automated market making bot for [Kalshi](https://kalshi.com) prediction markets, featuring an Avellaneda-Stoikov strategy adapted for binary event contracts and a full GUI control panel.

## Features

- **Avellaneda-Stoikov Strategy** - Optimal bid/ask quoting with inventory risk management, dynamic spread adjustment, and volatility-adaptive pricing
- **GUI Control Panel** - Real-time dashboard showing markets, positions, orders, P&L, and full settings management
- **Setup Wizard** - Step-by-step guided configuration for credentials, environment, and strategy parameters
- **Risk Management** - Position limits, daily loss limits, kill switch, and automatic order cancellation
- **Demo & Live Support** - Test safely on Kalshi's demo exchange before going live
- **Headless Mode** - Run without GUI for server deployments

## Strategy

The bot implements an **Avellaneda-Stoikov** market making framework adapted for Kalshi's binary event markets:

1. **Fair Value Estimation** - Computes microprice (volume-weighted mid) from the order book
2. **Optimal Spread** - Calculates spread based on volatility, inventory risk, and order arrival intensity
3. **Inventory Skew** - Adjusts reservation price away from accumulated position to naturally unwind risk
4. **Dynamic Sizing** - Reduces order sizes as inventory grows, with directional skew to rebalance
5. **Time Decay** - Widens spread as contract approaches expiry to reduce settlement risk

### Target Markets

The bot targets **weather markets** (e.g., NYC daily high temperature) which are ideal for market making:
- Daily expiry provides fresh opportunities every day
- Reasonable liquidity and volume
- Fair value can be independently estimated
- Consistent volatility patterns

## Quick Start

### 1. Install

```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Verify Python 3.10+ is installed
- Check/install Tkinter for the GUI
- Create a virtual environment
- Install all dependencies
- Create launcher scripts

### 2. Run

```bash
# Launch with GUI (opens setup wizard on first run)
./run.sh

# Re-run setup wizard
./run.sh --setup

# Headless mode (no GUI)
./run_headless.sh

# Verbose logging
./run.sh --verbose
```

### 3. Configure

On first launch, the setup wizard guides you through:
1. **Credentials** - Kalshi email and password
2. **Environment** - Demo (paper trading) or Live
3. **Strategy** - Order size, spreads, position limits, target markets

All settings are saved to `~/.kalshi_bot/` and can be changed later from the Settings tab.

## Architecture

```
kalshi_bot/
├── core/
│   ├── api.py           # Kalshi REST API client with auth and rate limiting
│   ├── config.py        # Configuration management and persistence
│   ├── engine.py        # Main bot loop orchestrating all components
│   ├── market_data.py   # Order book, trade history, volatility estimation
│   ├── order_manager.py # Order lifecycle (place, cancel, track)
│   └── risk_manager.py  # Position limits, P&L tracking, kill switch
├── strategy/
│   └── market_maker.py  # Avellaneda-Stoikov market making strategy
├── gui/
│   ├── control_panel.py # Tkinter dashboard with real-time updates
│   └── setup_wizard.py  # Step-by-step configuration wizard
└── main.py              # Entry point with CLI argument handling
```

## GUI Control Panel

The control panel provides:

- **Status Bar** - Bot state (running/paused/stopped), start/pause/stop/emergency stop controls
- **Stats Row** - Balance, daily P&L, position count, open orders, active markets, cycle count
- **Markets Tab** - Live view of all traded markets with bid/ask, fair value, spread, position, and time to expiry
- **Orders Tab** - All active orders with price, size, status, and age
- **Settings Tab** - Full strategy and risk parameter configuration
- **Log Tab** - Real-time log output from the bot engine

## Configuration

### Strategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_spread_cents` | 3 | Minimum bid-ask spread in cents |
| `max_spread_cents` | 15 | Maximum spread before skipping quotes |
| `order_size` | 5 | Base order size in contracts |
| `max_position` | 50 | Maximum position per market |
| `inventory_risk_aversion` | 0.3 | Avellaneda-Stoikov gamma parameter |
| `quote_refresh_seconds` | 5.0 | How often to update quotes |

### Risk Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_daily_loss_cents` | 5000 | Max daily loss before pausing ($50) |
| `kill_switch_loss_cents` | 10000 | Hard stop loss ($100) |
| `max_position_value_cents` | 25000 | Max total position value ($250) |
| `max_single_market_position` | 100 | Max contracts in any single market |

## Requirements

- Python 3.10+
- Tkinter (for GUI)
- Kalshi account (demo or live)

## Disclaimer

This software is for educational purposes. Trading involves risk of loss. Use demo mode for testing. The authors are not responsible for any financial losses incurred from using this software.
