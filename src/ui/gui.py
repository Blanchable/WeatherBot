"""Web-based GUI for the Kalshi Weather Bot using NiceGUI."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nicegui import ui, app, events

from src.bot.config import get_settings, reload_settings
from src.bot.logging import setup_logging, get_logger
from src.storage.db import Database
from src.storage.pnl import PnLTracker
from src.risk.limits import RiskLimits

log = get_logger(__name__)

_bot_instance = None
_bot_task: asyncio.Task | None = None
_log_messages: list[dict] = []
_MAX_LOG_LINES = 500


def _add_log(level: str, message: str) -> None:
    _log_messages.append({
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level,
        "message": message,
    })
    if len(_log_messages) > _MAX_LOG_LINES:
        _log_messages.pop(0)


class GUILogHandler:
    """Captures log messages for the GUI log panel."""

    def __init__(self):
        import logging
        self.handler = logging.Handler()
        self.handler.emit = self._emit

    def _emit(self, record) -> None:
        try:
            msg = record.getMessage()
            _add_log(record.levelname, msg)
        except Exception:
            pass

    def install(self) -> None:
        import logging
        root = logging.getLogger()
        root.addHandler(self.handler)


def _get_db() -> Database:
    db = Database()
    db.init_schema()
    return db


def _get_status() -> dict:
    if _bot_instance:
        return _bot_instance.get_status()
    db = _get_db()
    settings = get_settings()
    risk = RiskLimits(db, is_paper=True)
    pnl = PnLTracker(db, is_paper=True)
    exposure = risk.exposure_summary()
    pnl_data = pnl.sync_daily()
    db.close()
    return {
        "mode": "paper",
        "running": _bot_task is not None and not _bot_task.done(),
        "kill_switch": False,
        "kill_reason": None,
        "markets_tracked": 0,
        "active_orders": 0,
        **exposure,
        **pnl_data,
    }


def _get_positions(is_paper: bool = True) -> list[dict]:
    db = _get_db()
    positions = db.get_positions(is_paper)
    db.close()
    return positions


def _get_all_positions(is_paper: bool = True) -> list[dict]:
    db = _get_db()
    positions = db.get_all_positions(is_paper)
    db.close()
    return positions


def _get_orders(is_paper: bool = True) -> list[dict]:
    db = _get_db()
    orders = db.get_open_orders(is_paper)
    db.close()
    return orders


def _get_pnl_history(days: int = 30, is_paper: bool = True) -> list[dict]:
    db = _get_db()
    history = db.get_daily_pnl_history(days, is_paper)
    db.close()
    return history


def _get_fills_today(is_paper: bool = True) -> list[dict]:
    db = _get_db()
    fills = db.get_fills_today(is_paper)
    db.close()
    return fills


async def _start_bot(is_paper: bool = True) -> None:
    global _bot_instance, _bot_task
    if _bot_task and not _bot_task.done():
        _add_log("WARNING", "Bot is already running")
        return

    from src.bot.main import WeatherBot
    _bot_instance = WeatherBot(is_paper=is_paper)
    _bot_task = asyncio.create_task(_bot_instance.start())
    _add_log("INFO", f"Bot started in {'PAPER' if is_paper else 'LIVE'} mode")


async def _stop_bot() -> None:
    global _bot_instance, _bot_task
    if _bot_instance:
        await _bot_instance.stop()
        _add_log("INFO", "Bot stopped")
    _bot_instance = None
    _bot_task = None


def launch_gui(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Launch the NiceGUI web interface."""
    setup_logging("INFO")
    log_handler = GUILogHandler()
    log_handler.install()

    @ui.page("/")
    async def main_page():
        ui.add_head_html("""
        <style>
            body { background-color: #0f1117 !important; }
            .nicegui-content { max-width: 1400px; margin: 0 auto; }
            .stat-card { background: #1a1d29; border-radius: 12px; padding: 16px; }
            .dark-panel { background: #1a1d29; border-radius: 12px; }
        </style>
        """)
        ui.dark_mode().enable()

        # Header
        with ui.row().classes("w-full items-center justify-between p-4"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("thermostat", size="lg").classes("text-blue-400")
                ui.label("Kalshi Weather Bot").classes("text-2xl font-bold text-white")
            with ui.row().classes("items-center gap-2"):
                status_badge = ui.badge("STOPPED", color="red").classes("text-sm")
                mode_badge = ui.badge("PAPER", color="blue").classes("text-sm")

        ui.separator()

        # Controls row
        with ui.row().classes("w-full items-center gap-4 px-4 py-2"):
            paper_btn = ui.button("Start Paper", icon="play_arrow", color="green",
                                  on_click=lambda: _start_bot(True))
            live_btn = ui.button("Start Live", icon="rocket_launch", color="orange",
                                 on_click=lambda: _start_bot(False))
            stop_btn = ui.button("Stop Bot", icon="stop", color="red",
                                 on_click=_stop_bot)
            kill_reset_btn = ui.button("Reset Kill Switch", icon="refresh", color="yellow")

            async def _reset_kill():
                if _bot_instance:
                    _bot_instance.kill_switch.reset()
                    _add_log("INFO", "Kill switch reset")
            kill_reset_btn.on_click(_reset_kill)

        # ── Stats row ──────────────────────────────────────
        with ui.row().classes("w-full gap-4 px-4"):
            with ui.card().classes("stat-card flex-1"):
                pnl_label = ui.label("$0.00").classes("text-3xl font-bold text-green-400")
                ui.label("Realized P&L").classes("text-sm text-gray-400")
            with ui.card().classes("stat-card flex-1"):
                unr_pnl_label = ui.label("$0.00").classes("text-3xl font-bold text-blue-400")
                ui.label("Unrealized P&L").classes("text-sm text-gray-400")
            with ui.card().classes("stat-card flex-1"):
                fees_label = ui.label("$0.00").classes("text-3xl font-bold text-yellow-400")
                ui.label("Fees Today").classes("text-sm text-gray-400")
            with ui.card().classes("stat-card flex-1"):
                exposure_label = ui.label("$0.00").classes("text-3xl font-bold text-orange-400")
                ui.label("Gross Exposure").classes("text-sm text-gray-400")
            with ui.card().classes("stat-card flex-1"):
                markets_label = ui.label("0").classes("text-3xl font-bold text-purple-400")
                ui.label("Markets Tracked").classes("text-sm text-gray-400")

        # ── Tabs ────────────────────────────────────────────
        with ui.tabs().classes("w-full px-4") as tabs:
            tab_chart = ui.tab("Performance", icon="show_chart")
            tab_positions = ui.tab("Positions", icon="account_balance")
            tab_orders = ui.tab("Orders", icon="list_alt")
            tab_fills = ui.tab("Fills", icon="receipt")
            tab_logs = ui.tab("Logs", icon="terminal")
            tab_settings = ui.tab("Settings", icon="settings")

        with ui.tab_panels(tabs, value=tab_chart).classes("w-full px-4"):
            # ── Performance Chart ───────────────────────────
            with ui.tab_panel(tab_chart):
                chart = ui.chart({
                    "title": {"text": "Cumulative P&L", "style": {"color": "#fff"}},
                    "chart": {"type": "area", "backgroundColor": "#1a1d29"},
                    "xAxis": {
                        "categories": [],
                        "labels": {"style": {"color": "#999"}},
                    },
                    "yAxis": {
                        "title": {"text": "P&L ($)", "style": {"color": "#999"}},
                        "labels": {"style": {"color": "#999"}},
                        "gridLineColor": "#333",
                    },
                    "series": [{
                        "name": "Net P&L",
                        "data": [],
                        "color": "#22c55e",
                        "fillColor": {
                            "linearGradient": {"x1": 0, "y1": 0, "x2": 0, "y2": 1},
                            "stops": [[0, "rgba(34,197,94,0.3)"], [1, "rgba(34,197,94,0)"]],
                        },
                    }, {
                        "name": "Fees",
                        "data": [],
                        "color": "#eab308",
                        "type": "column",
                    }],
                    "legend": {"itemStyle": {"color": "#ccc"}},
                    "plotOptions": {"area": {"marker": {"enabled": True, "radius": 3}}},
                }).classes("w-full h-80")

            # ── Positions ───────────────────────────────────
            with ui.tab_panel(tab_positions):
                positions_table = ui.table(
                    columns=[
                        {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left"},
                        {"name": "side", "label": "Side", "field": "side"},
                        {"name": "quantity", "label": "Qty", "field": "quantity", "sortable": True},
                        {"name": "avg_price", "label": "Avg Price", "field": "avg_price"},
                        {"name": "unrealized", "label": "Unrealized", "field": "unrealized"},
                        {"name": "realized", "label": "Realized", "field": "realized"},
                    ],
                    rows=[],
                ).classes("w-full")

            # ── Orders ──────────────────────────────────────
            with ui.tab_panel(tab_orders):
                orders_table = ui.table(
                    columns=[
                        {"name": "order_id", "label": "Order ID", "field": "order_id", "align": "left"},
                        {"name": "ticker", "label": "Ticker", "field": "ticker"},
                        {"name": "side", "label": "Side", "field": "side"},
                        {"name": "action", "label": "Action", "field": "action"},
                        {"name": "price", "label": "Price", "field": "price"},
                        {"name": "qty", "label": "Qty", "field": "qty"},
                        {"name": "prob", "label": "Model Prob", "field": "prob"},
                        {"name": "ev", "label": "EV", "field": "ev"},
                    ],
                    rows=[],
                ).classes("w-full")

            # ── Fills ───────────────────────────────────────
            with ui.tab_panel(tab_fills):
                fills_table = ui.table(
                    columns=[
                        {"name": "fill_id", "label": "Fill ID", "field": "fill_id", "align": "left"},
                        {"name": "ticker", "label": "Ticker", "field": "ticker"},
                        {"name": "side", "label": "Side", "field": "side"},
                        {"name": "action", "label": "Action", "field": "action"},
                        {"name": "price", "label": "Price", "field": "price"},
                        {"name": "qty", "label": "Qty", "field": "qty"},
                        {"name": "fee", "label": "Fee", "field": "fee"},
                        {"name": "time", "label": "Time", "field": "time"},
                    ],
                    rows=[],
                ).classes("w-full")

            # ── Logs ────────────────────────────────────────
            with ui.tab_panel(tab_logs):
                log_area = ui.textarea(
                    value="",
                ).classes("w-full font-mono text-xs").props('readonly rows=25 dark')

            # ── Settings ────────────────────────────────────
            with ui.tab_panel(tab_settings):
                settings = get_settings()
                with ui.grid(columns=2).classes("w-full gap-4"):
                    with ui.card().classes("dark-panel p-4"):
                        ui.label("Trading Parameters").classes("text-lg font-bold mb-2")
                        min_spread = ui.number("Min Spread (cents)", value=settings.min_spread_cents, min=1, max=50)
                        min_volume = ui.number("Min 24h Volume", value=settings.min_24h_volume, min=0)
                        min_ev = ui.number("Min EV ($/contract)", value=settings.min_ev_dollars_per_contract,
                                           min=0, step=0.005, format="%.3f")
                        max_markets_input = ui.number("Max Markets", value=settings.max_markets, min=1, max=50)
                        refresh_secs = ui.number("Refresh Seconds", value=settings.refresh_seconds, min=5, max=300)

                    with ui.card().classes("dark-panel p-4"):
                        ui.label("Risk Limits").classes("text-lg font-bold mb-2")
                        max_gross = ui.number("Max Gross Exposure ($)", value=settings.max_gross_exposure_dollars)
                        max_net = ui.number("Max Net Exposure ($)", value=settings.max_net_exposure_dollars)
                        max_city = ui.number("Max Per-City ($)", value=settings.max_exposure_per_city_dollars)
                        max_market = ui.number("Max Per-Market ($)", value=settings.max_exposure_per_market_dollars)
                        max_order = ui.number("Max Order Size", value=settings.max_order_size_contracts, min=1)

                    with ui.card().classes("dark-panel p-4"):
                        ui.label("P&L Limits").classes("text-lg font-bold mb-2")
                        daily_stop = ui.number("Daily Stop Loss ($)", value=settings.daily_stop_loss_dollars)
                        daily_tp = ui.number("Daily Take Profit ($)", value=settings.daily_take_profit_dollars)
                        tp_cents = ui.number("Take Profit (cents)", value=settings.take_profit_cents, min=1)
                        sl_cents = ui.number("Stop Loss (cents)", value=settings.stop_loss_cents, min=1)

                    with ui.card().classes("dark-panel p-4"):
                        ui.label("Forecast Model").classes("text-lg font-bold mb-2")
                        sigma_same = ui.number("Sigma Same-Day (°F)", value=settings.sigma_same_day,
                                               min=0.1, step=0.1, format="%.1f")
                        sigma_next = ui.number("Sigma Next-Day (°F)", value=settings.sigma_next_day,
                                               min=0.1, step=0.1, format="%.1f")
                        sigma_2p = ui.number("Sigma 2+ Days (°F)", value=settings.sigma_2plus_day,
                                             min=0.1, step=0.1, format="%.1f")

                def _save_settings():
                    import os
                    os.environ["MIN_SPREAD_CENTS"] = str(int(min_spread.value))
                    os.environ["MIN_24H_VOLUME"] = str(int(min_volume.value))
                    os.environ["MIN_EV_DOLLARS_PER_CONTRACT"] = str(min_ev.value)
                    os.environ["MAX_MARKETS"] = str(int(max_markets_input.value))
                    os.environ["REFRESH_SECONDS"] = str(int(refresh_secs.value))
                    os.environ["MAX_GROSS_EXPOSURE_DOLLARS"] = str(max_gross.value)
                    os.environ["MAX_NET_EXPOSURE_DOLLARS"] = str(max_net.value)
                    os.environ["MAX_EXPOSURE_PER_CITY_DOLLARS"] = str(max_city.value)
                    os.environ["MAX_EXPOSURE_PER_MARKET_DOLLARS"] = str(max_market.value)
                    os.environ["MAX_ORDER_SIZE_CONTRACTS"] = str(int(max_order.value))
                    os.environ["DAILY_STOP_LOSS_DOLLARS"] = str(daily_stop.value)
                    os.environ["DAILY_TAKE_PROFIT_DOLLARS"] = str(daily_tp.value)
                    os.environ["TAKE_PROFIT_CENTS"] = str(int(tp_cents.value))
                    os.environ["STOP_LOSS_CENTS"] = str(int(sl_cents.value))
                    os.environ["SIGMA_SAME_DAY"] = str(sigma_same.value)
                    os.environ["SIGMA_NEXT_DAY"] = str(sigma_next.value)
                    os.environ["SIGMA_2PLUS_DAY"] = str(sigma_2p.value)
                    reload_settings()
                    ui.notify("Settings saved", type="positive")

                ui.button("Save Settings", icon="save", on_click=_save_settings).classes("mt-4")

        # ── Auto-refresh timer ──────────────────────────────

        async def _refresh():
            try:
                status = _get_status()

                # Update badges
                is_running = status.get("running", False)
                status_badge.text = "RUNNING" if is_running else "STOPPED"
                status_badge._props["color"] = "green" if is_running else "red"
                status_badge.update()

                mode_text = status.get("mode", "paper").upper()
                mode_badge.text = mode_text
                mode_badge._props["color"] = "blue" if mode_text == "PAPER" else "orange"
                mode_badge.update()

                # Update stat cards
                realized = status.get("realized_pnl", 0)
                pnl_label.text = f"${realized:+.2f}"
                pnl_label.classes(replace="text-3xl font-bold " + ("text-green-400" if realized >= 0 else "text-red-400"))

                unrealized = status.get("unrealized_pnl", 0)
                unr_pnl_label.text = f"${unrealized:+.2f}"

                fees_val = status.get("fees", 0)
                fees_label.text = f"${fees_val:.2f}"

                gross = status.get("gross_exposure", 0)
                exposure_label.text = f"${gross:.2f}"

                markets_label.text = str(status.get("markets_tracked", 0))

                # Update positions table
                positions = _get_positions()
                positions_table.rows = [
                    {
                        "ticker": p["ticker"],
                        "side": p["side"].upper(),
                        "quantity": p["quantity"],
                        "avg_price": f"{p['avg_price_cents']:.0f}c",
                        "unrealized": f"${p.get('unrealized_pnl', 0):.2f}",
                        "realized": f"${p.get('realized_pnl', 0):.2f}",
                    }
                    for p in positions
                ]

                # Update orders table
                orders = _get_orders()
                orders_table.rows = [
                    {
                        "order_id": o["order_id"][:16],
                        "ticker": o["ticker"],
                        "side": o["side"].upper(),
                        "action": o["action"].upper(),
                        "price": f"{o['price_cents']}c",
                        "qty": o["quantity"],
                        "prob": f"{o.get('model_prob', 0):.2%}" if o.get("model_prob") else "—",
                        "ev": f"${o.get('model_ev', 0):.4f}" if o.get("model_ev") else "—",
                    }
                    for o in orders
                ]

                # Update fills table
                fills = _get_fills_today()
                fills_table.rows = [
                    {
                        "fill_id": f["fill_id"][:16],
                        "ticker": f["ticker"],
                        "side": f["side"].upper(),
                        "action": f["action"].upper(),
                        "price": f"{f['price_cents']}c",
                        "qty": f["quantity"],
                        "fee": f"${f['fee_dollars']:.4f}",
                        "time": f["filled_at"][11:19] if len(f["filled_at"]) > 19 else f["filled_at"],
                    }
                    for f in fills
                ]

                # Update chart
                history = _get_pnl_history(30)
                if history:
                    history.reverse()
                    dates = [h["date_utc"] for h in history]
                    cumulative = []
                    running = 0.0
                    for h in history:
                        running += h["realized_pnl"] - h["fees_paid"]
                        cumulative.append(round(running, 2))
                    fees_data = [round(h["fees_paid"], 2) for h in history]

                    chart.options["xAxis"]["categories"] = dates
                    chart.options["series"][0]["data"] = cumulative
                    chart.options["series"][1]["data"] = fees_data
                    chart.update()

                # Update logs
                log_lines = [
                    f"[{m['time']}] {m['level']}: {m['message']}"
                    for m in _log_messages[-200:]
                ]
                log_area.value = "\n".join(log_lines)

            except Exception as exc:
                _add_log("ERROR", f"GUI refresh error: {exc}")

        ui.timer(5.0, _refresh)

    ui.run(
        host=host,
        port=port,
        title="Kalshi Weather Bot",
        dark=True,
        reload=False,
        show=False,
    )
