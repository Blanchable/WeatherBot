"""Tkinter GUI for monitoring and controlling the weather bot."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Protocol


class BotController(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def update_settings(self, settings: dict[str, str]) -> None: ...

    def snapshot(self) -> dict: ...


class MockController:
    def __init__(self) -> None:
        self._running = False
        self._lock = threading.Lock()
        self._state = {
            "running": False,
            "mode": "paper",
            "daily_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "gross_exposure": 0.0,
            "net_exposure": 0.0,
            "positions": [],
            "settings": {},
        }

    def start(self) -> None:
        with self._lock:
            self._running = True
            self._state["running"] = True

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._state["running"] = False

    def update_settings(self, settings: dict[str, str]) -> None:
        with self._lock:
            self._state["settings"] = settings

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)


class WeatherBotGUI(tk.Tk):
    def __init__(self, controller: BotController) -> None:
        super().__init__()
        self.title("Kalshi Weather Bot")
        self.geometry("900x560")
        self.controller = controller

        self.status_var = tk.StringVar(value="Stopped")
        self.mode_var = tk.StringVar(value="paper")
        self.pnl_var = tk.StringVar(value="$0.00")
        self.unrealized_var = tk.StringVar(value="$0.00")
        self.gross_var = tk.StringVar(value="$0.00")
        self.net_var = tk.StringVar(value="$0.00")

        self.refresh_seconds_var = tk.StringVar(value="20")
        self.min_ev_var = tk.StringVar(value="0.02")
        self.max_markets_var = tk.StringVar(value="8")
        self.cities_var = tk.StringVar(value="NYC,LA,CHI")

        self._build_layout()
        self.after(1000, self._refresh)

    def _build_layout(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Status:").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(top, text="Mode:").grid(row=0, column=2, sticky="w")
        ttk.Label(top, textvariable=self.mode_var).grid(row=0, column=3, sticky="w", padx=8)

        ttk.Button(top, text="Start", command=self._start).grid(row=0, column=4, padx=5)
        ttk.Button(top, text="Stop", command=self._stop).grid(row=0, column=5, padx=5)
        ttk.Button(top, text="Apply Settings", command=self._apply_settings).grid(row=0, column=6, padx=5)

        perf = ttk.LabelFrame(self, text="Performance", padding=10)
        perf.pack(fill="x", padx=10, pady=10)
        ttk.Label(perf, text="Daily PnL").grid(row=0, column=0, sticky="w")
        ttk.Label(perf, textvariable=self.pnl_var).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(perf, text="Unrealized").grid(row=0, column=2, sticky="w")
        ttk.Label(perf, textvariable=self.unrealized_var).grid(row=0, column=3, sticky="w", padx=8)
        ttk.Label(perf, text="Gross Exposure").grid(row=1, column=0, sticky="w")
        ttk.Label(perf, textvariable=self.gross_var).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(perf, text="Net Exposure").grid(row=1, column=2, sticky="w")
        ttk.Label(perf, textvariable=self.net_var).grid(row=1, column=3, sticky="w", padx=8)

        settings = ttk.LabelFrame(self, text="Settings", padding=10)
        settings.pack(fill="x", padx=10, pady=10)
        ttk.Label(settings, text="Refresh Seconds").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.refresh_seconds_var, width=10).grid(row=0, column=1, padx=8)
        ttk.Label(settings, text="Min EV ($/contract)").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.min_ev_var, width=10).grid(row=0, column=3, padx=8)
        ttk.Label(settings, text="Max Markets").grid(row=1, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.max_markets_var, width=10).grid(row=1, column=1, padx=8)
        ttk.Label(settings, text="Cities").grid(row=1, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.cities_var, width=30).grid(row=1, column=3, padx=8)

        positions_frame = ttk.LabelFrame(self, text="Positions", padding=10)
        positions_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.positions_table = ttk.Treeview(
            positions_frame,
            columns=("ticker", "city", "contracts", "avg", "realized"),
            show="headings",
        )
        for col, title in [
            ("ticker", "Ticker"),
            ("city", "City"),
            ("contracts", "Contracts"),
            ("avg", "Avg Price"),
            ("realized", "Realized PnL"),
        ]:
            self.positions_table.heading(col, text=title)
            self.positions_table.column(col, width=120, anchor="center")
        self.positions_table.pack(fill="both", expand=True)

    def _start(self) -> None:
        self.controller.start()

    def _stop(self) -> None:
        self.controller.stop()

    def _apply_settings(self) -> None:
        self.controller.update_settings(
            {
                "refresh_seconds": self.refresh_seconds_var.get(),
                "min_ev_dollars_per_contract": self.min_ev_var.get(),
                "max_markets": self.max_markets_var.get(),
                "cities": self.cities_var.get(),
            }
        )

    def _refresh(self) -> None:
        data = self.controller.snapshot()
        self.status_var.set("Running" if data.get("running") else "Stopped")
        self.mode_var.set(data.get("mode", "paper"))
        self.pnl_var.set(f"${float(data.get('daily_pnl', 0.0)):.2f}")
        self.unrealized_var.set(f"${float(data.get('unrealized_pnl', 0.0)):.2f}")
        self.gross_var.set(f"${float(data.get('gross_exposure', 0.0)):.2f}")
        self.net_var.set(f"${float(data.get('net_exposure', 0.0)):.2f}")

        for item in self.positions_table.get_children():
            self.positions_table.delete(item)
        for pos in data.get("positions", []):
            self.positions_table.insert(
                "",
                tk.END,
                values=(
                    pos.get("ticker", ""),
                    pos.get("city_id", ""),
                    pos.get("contracts", 0),
                    f"{pos.get('avg_price_cents', 0)}c",
                    f"${float(pos.get('realized_pnl_dollars', 0.0)):.2f}",
                ),
            )
        self.after(1000, self._refresh)


def main() -> None:
    app = WeatherBotGUI(controller=MockController())
    app.mainloop()


if __name__ == "__main__":
    main()

