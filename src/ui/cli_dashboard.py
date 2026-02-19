"""Rich CLI dashboard for the weather bot."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.bot.config import get_settings
from src.storage.db import Database


console = Console()


def make_status_panel(status: dict) -> Panel:
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold cyan")
    tbl.add_column("Value")

    mode_color = "green" if status.get("mode") == "paper" else "red bold"
    tbl.add_row("Mode", Text(status.get("mode", "?").upper(), style=mode_color))
    tbl.add_row("Running", "Yes" if status.get("running") else "No")
    tbl.add_row("Kill Switch", Text("ACTIVE", style="red bold") if status.get("kill_switch") else "OK")
    tbl.add_row("Markets Tracked", str(status.get("markets_tracked", 0)))
    tbl.add_row("Active Orders", str(status.get("active_orders", 0)))
    tbl.add_row("Open Positions", str(status.get("open_positions", 0)))

    return Panel(tbl, title="Bot Status", border_style="blue")


def make_exposure_panel(status: dict) -> Panel:
    settings = get_settings()
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Current")
    tbl.add_column("Limit")

    gross = status.get("gross_exposure", 0)
    net = status.get("net_exposure", 0)
    tbl.add_row(
        "Gross Exposure",
        f"${gross:.2f}",
        f"${settings.max_gross_exposure_dollars:.0f}",
    )
    tbl.add_row(
        "Net Exposure",
        f"${net:.2f}",
        f"${settings.max_net_exposure_dollars:.0f}",
    )

    by_city = status.get("by_city", {})
    for city, exp in sorted(by_city.items()):
        tbl.add_row(f"  {city}", f"${exp:.2f}", f"${settings.max_exposure_per_city_dollars:.0f}")

    return Panel(tbl, title="Exposure", border_style="yellow")


def make_pnl_panel(status: dict) -> Panel:
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value")

    realized = status.get("realized_pnl", 0)
    unrealized = status.get("unrealized_pnl", 0)
    fees = status.get("fees", 0)
    color = "green" if realized >= 0 else "red"

    tbl.add_row("Realized P&L", Text(f"${realized:.2f}", style=color))
    tbl.add_row("Unrealized P&L", f"${unrealized:.2f}")
    tbl.add_row("Fees Today", f"${fees:.2f}")
    tbl.add_row("Net P&L", Text(f"${realized + unrealized - fees:.2f}", style=color))
    tbl.add_row("Fills Today", str(status.get("num_fills", 0)))

    return Panel(tbl, title="Daily P&L", border_style="green")


def make_positions_table(db: Database, is_paper: bool = True) -> Panel:
    positions = db.get_positions(is_paper)
    tbl = Table(title="Open Positions")
    tbl.add_column("Ticker", style="cyan")
    tbl.add_column("Side")
    tbl.add_column("Qty", justify="right")
    tbl.add_column("Avg Price", justify="right")
    tbl.add_column("Unrealized", justify="right")
    tbl.add_column("Realized", justify="right")

    for p in positions:
        side_style = "green" if p["side"] == "yes" else "red"
        rpnl = p.get("realized_pnl", 0)
        rpnl_style = "green" if rpnl >= 0 else "red"
        tbl.add_row(
            p["ticker"],
            Text(p["side"].upper(), style=side_style),
            str(p["quantity"]),
            f"{p['avg_price_cents']:.0f}c",
            f"${p.get('unrealized_pnl', 0):.2f}",
            Text(f"${rpnl:.2f}", style=rpnl_style),
        )

    if not positions:
        tbl.add_row("—", "—", "—", "—", "—", "—")

    return Panel(tbl, border_style="magenta")


def make_orders_table(db: Database, is_paper: bool = True) -> Panel:
    orders = db.get_open_orders(is_paper)
    tbl = Table(title="Active Orders")
    tbl.add_column("Order ID", style="dim")
    tbl.add_column("Ticker", style="cyan")
    tbl.add_column("Side")
    tbl.add_column("Action")
    tbl.add_column("Price", justify="right")
    tbl.add_column("Qty", justify="right")
    tbl.add_column("Prob", justify="right")
    tbl.add_column("EV", justify="right")

    for o in orders[:20]:
        tbl.add_row(
            o["order_id"][:12] + "...",
            o["ticker"],
            o["side"].upper(),
            o["action"].upper(),
            f"{o['price_cents']}c",
            str(o["quantity"]),
            f"{o.get('model_prob', 0):.2%}" if o.get("model_prob") else "—",
            f"${o.get('model_ev', 0):.4f}" if o.get("model_ev") else "—",
        )

    if not orders:
        tbl.add_row("—", "—", "—", "—", "—", "—", "—", "—")

    return Panel(tbl, border_style="blue")


def make_pnl_history_table(db: Database, is_paper: bool = True) -> Panel:
    history = db.get_daily_pnl_history(14, is_paper)
    tbl = Table(title="P&L History (last 14 days)")
    tbl.add_column("Date")
    tbl.add_column("Realized", justify="right")
    tbl.add_column("Fees", justify="right")
    tbl.add_column("Net", justify="right")
    tbl.add_column("Trades", justify="right")

    for row in history:
        net = row["realized_pnl"] - row["fees_paid"]
        color = "green" if net >= 0 else "red"
        tbl.add_row(
            row["date_utc"],
            f"${row['realized_pnl']:.2f}",
            f"${row['fees_paid']:.2f}",
            Text(f"${net:.2f}", style=color),
            str(row["num_trades"]),
        )

    return Panel(tbl, border_style="cyan")


def print_dashboard(status: dict, db: Database, is_paper: bool = True) -> None:
    console.clear()
    console.print()
    console.print(
        Text("Kalshi Weather Bot", style="bold white on blue", justify="center"),
        justify="center",
    )
    console.print(
        Text(
            f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            style="dim",
        ),
        justify="center",
    )
    console.print()

    console.print(make_status_panel(status))
    console.print(make_exposure_panel(status))
    console.print(make_pnl_panel(status))
    console.print(make_positions_table(db, is_paper))
    console.print(make_orders_table(db, is_paper))
    console.print(make_pnl_history_table(db, is_paper))
