"""Interactive setup wizard for the Kalshi Weather Bot.

Can be run directly (python setup_wizard.py) or via the batch/shell launcher.
Bootstraps its own dependencies before importing anything heavy.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def _bootstrap() -> None:
    """Install the project (and all deps) if rich is not yet available."""
    try:
        import rich  # noqa: F401
    except ImportError:
        print("\n  First-time setup: installing dependencies...")
        print(f"  Project root: {PROJECT_ROOT}\n")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)],
        )
        print("\n  Dependencies installed. Continuing setup...\n")


_bootstrap()

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.prompt import Prompt, Confirm, IntPrompt, FloatPrompt  # noqa: E402
from rich.text import Text  # noqa: E402
from rich.table import Table  # noqa: E402

console = Console()


def _banner() -> None:
    console.print()
    console.print(Panel(
        Text("Kalshi Weather Bot — Setup Wizard", style="bold white", justify="center"),
        border_style="blue",
        padding=(1, 4),
    ))
    console.print()


def _check_python() -> bool:
    version = sys.version_info
    ok = version >= (3, 11)
    status = "[green]OK[/green]" if ok else "[red]FAIL (need 3.11+)[/red]"
    console.print(f"  Python {version.major}.{version.minor}.{version.micro} ... {status}")
    return ok


def _check_deps() -> bool:
    missing = []
    for pkg in ["httpx", "pydantic", "rich", "numpy", "scipy", "cryptography", "click", "nicegui"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        console.print(f"  [yellow]Missing packages: {', '.join(missing)}[/yellow]")
        if Confirm.ask("  Install missing dependencies now?", default=True):
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
                console.print("  [green]Dependencies installed successfully[/green]")
                return True
            except subprocess.CalledProcessError:
                console.print("  [red]Failed to install dependencies[/red]")
                console.print(f"  Try manually: pip install -e {PROJECT_ROOT}")
                return False
    else:
        console.print("  [green]All dependencies present[/green]")
    return True


def _setup_api_keys() -> dict:
    console.print()
    console.print(Panel("Step 1: Kalshi API Configuration", border_style="cyan"))
    console.print()
    console.print("  You need a Kalshi API key pair. Generate one at:")
    console.print("  [link]https://kalshi.com/account/api[/link]")
    console.print()

    env_choice = Prompt.ask(
        "  Kalshi environment",
        choices=["prod", "demo"],
        default="prod",
    )

    rest_base = Prompt.ask(
        "  REST API base URL",
        default="https://api.elections.kalshi.com/trade-api/v2",
    )

    key_id = Prompt.ask("  API Key ID", default="")

    pk_path = Prompt.ask(
        "  Private key file path",
        default=str(PROJECT_ROOT / "kalshi_private_key.pem"),
    )

    if key_id and not Path(pk_path).exists():
        console.print(f"  [yellow]Warning: Private key file not found at {pk_path}[/yellow]")
        console.print("  Please place your private key there before running the bot.")

    return {
        "KALSHI_ENV": env_choice,
        "KALSHI_REST_BASE": rest_base,
        "KALSHI_KEY_ID": key_id,
        "KALSHI_PRIVATE_KEY_PATH": pk_path,
    }


def _setup_trading_params() -> dict:
    console.print()
    console.print(Panel("Step 2: Trading Parameters", border_style="cyan"))
    console.print()

    cities = Prompt.ask(
        "  Cities to trade (comma-separated codes)",
        default="NYC,LA,CHI",
    )

    bankroll = FloatPrompt.ask("  Starting bankroll ($)", default=1400.0)
    max_markets = IntPrompt.ask("  Max simultaneous markets", default=8)
    refresh = IntPrompt.ask("  Refresh interval (seconds)", default=20)

    return {
        "CITIES": cities,
        "START_BANKROLL_DOLLARS": str(bankroll),
        "MAX_MARKETS": str(max_markets),
        "REFRESH_SECONDS": str(refresh),
    }


def _setup_risk_params() -> dict:
    console.print()
    console.print(Panel("Step 3: Risk Management", border_style="cyan"))
    console.print()

    console.print("  [dim]Defaults are conservative. Adjust after paper-trading.[/dim]")
    console.print()

    max_gross = FloatPrompt.ask("  Max gross exposure ($)", default=250.0)
    max_net = FloatPrompt.ask("  Max net exposure ($)", default=150.0)
    max_city = FloatPrompt.ask("  Max per-city exposure ($)", default=125.0)
    max_market = FloatPrompt.ask("  Max per-market exposure ($)", default=75.0)
    max_order = IntPrompt.ask("  Max order size (contracts)", default=10)
    daily_stop = FloatPrompt.ask("  Daily stop-loss ($)", default=50.0)
    daily_tp = FloatPrompt.ask("  Daily take-profit ($)", default=40.0)
    min_spread = IntPrompt.ask("  Minimum spread (cents)", default=6)
    min_ev = FloatPrompt.ask("  Minimum EV ($/contract)", default=0.02)

    return {
        "MAX_GROSS_EXPOSURE_DOLLARS": str(max_gross),
        "MAX_NET_EXPOSURE_DOLLARS": str(max_net),
        "MAX_EXPOSURE_PER_CITY_DOLLARS": str(max_city),
        "MAX_EXPOSURE_PER_MARKET_DOLLARS": str(max_market),
        "MAX_ORDER_SIZE_CONTRACTS": str(max_order),
        "DAILY_STOP_LOSS_DOLLARS": str(daily_stop),
        "DAILY_TAKE_PROFIT_DOLLARS": str(daily_tp),
        "MIN_SPREAD_CENTS": str(min_spread),
        "MIN_EV_DOLLARS_PER_CONTRACT": str(min_ev),
    }


def _setup_mode() -> dict:
    console.print()
    console.print(Panel("Step 4: Operating Mode", border_style="cyan"))
    console.print()

    live = Confirm.ask(
        "  Enable LIVE trading? (default: paper only)",
        default=False,
    )
    maker_only = Confirm.ask(
        "  Maker-only orders? (recommended: yes)",
        default=True,
    )

    return {
        "LIVE_TRADING": str(live).lower(),
        "MAKER_ONLY": str(maker_only).lower(),
        "BOT_MODE": "weather",
    }


def _write_env(all_config: dict) -> None:
    defaults = {
        "NO_TRADE_WINDOW_SECONDS": "21600",
        "EXIT_ONLY_WINDOW_SECONDS": "10800",
        "MIN_24H_VOLUME": "500",
        "TAKE_PROFIT_CENTS": "4",
        "STOP_LOSS_CENTS": "6",
        "FORECAST_STALE_MINUTES_SAME_DAY": "30",
        "FORECAST_STALE_MINUTES_NEXT_DAY": "180",
    }

    merged = {**defaults, **all_config}

    lines = ["# Kalshi Weather Bot - Auto-generated Configuration", ""]
    for key, val in merged.items():
        lines.append(f"{key}={val}")
    lines.append("")

    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"\n  [green]Configuration written to {ENV_FILE}[/green]")


def _show_summary(config: dict) -> None:
    console.print()
    tbl = Table(title="Configuration Summary")
    tbl.add_column("Setting", style="cyan")
    tbl.add_column("Value")

    for k, v in config.items():
        display_v = v
        if "KEY" in k.upper() and v and len(v) > 8:
            display_v = v[:4] + "..." + v[-4:]
        if "PRIVATE" in k.upper() and "PATH" in k.upper():
            display_v = v
        tbl.add_row(k, display_v)

    console.print(tbl)


def _launch_prompt() -> None:
    console.print()
    console.print(Panel("Setup Complete!", border_style="green"))
    console.print()
    console.print("  Next steps:")
    console.print("  1. Place your private key at the configured path")
    console.print("  2. Run paper trading first:")
    console.print("     [bold]python -m src.bot.main --mode paper[/bold]")
    console.print("  3. Or launch the GUI:")
    console.print("     [bold]python -m src.ui.gui[/bold]")
    console.print()

    if Confirm.ask("  Launch the GUI now?", default=True):
        console.print("  Starting GUI on http://localhost:8080 ...")
        from src.ui.gui import launch_gui
        launch_gui()


def main() -> None:
    _banner()

    console.print(Panel("Checking Prerequisites", border_style="yellow"))
    python_ok = _check_python()
    if not python_ok:
        console.print("[red]Python 3.11+ is required. Please upgrade.[/red]")
        sys.exit(1)

    deps_ok = _check_deps()
    if not deps_ok:
        if not Confirm.ask("Continue anyway?", default=False):
            sys.exit(1)

    config: dict = {}

    api_config = _setup_api_keys()
    config.update(api_config)

    trading_config = _setup_trading_params()
    config.update(trading_config)

    risk_config = _setup_risk_params()
    config.update(risk_config)

    mode_config = _setup_mode()
    config.update(mode_config)

    _show_summary(config)

    if Confirm.ask("\n  Save this configuration?", default=True):
        _write_env(config)

    _launch_prompt()


if __name__ == "__main__":
    main()
