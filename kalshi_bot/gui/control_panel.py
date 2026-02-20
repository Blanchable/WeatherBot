"""Main GUI control panel for the Kalshi Market Making Bot."""

import logging
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

from kalshi_bot.core.config import BotConfig, Credentials
from kalshi_bot.core.engine import BotEngine

logger = logging.getLogger(__name__)

COLORS = {
    "bg": "#1a1b26",
    "bg_secondary": "#24283b",
    "bg_tertiary": "#2f3348",
    "text": "#c0caf5",
    "text_dim": "#565f89",
    "accent": "#7aa2f7",
    "green": "#9ece6a",
    "red": "#f7768e",
    "yellow": "#e0af68",
    "orange": "#ff9e64",
    "border": "#3b4261",
}


class ControlPanel:
    """Tkinter-based control panel for the market making bot."""

    def __init__(self, config: BotConfig, credentials: Credentials):
        self.config = config
        self.credentials = credentials
        self.engine: Optional[BotEngine] = None
        self._update_job = None

        self.root = tk.Tk()
        self.root.title("Kalshi Market Making Bot")
        self.root.geometry("1100x780")
        self.root.minsize(900, 650)
        self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._setup_styles()
        self._build_ui()
        self._setup_log_handler()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"],
                        fieldbackground=COLORS["bg_secondary"], bordercolor=COLORS["border"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["bg_secondary"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground=COLORS["accent"])
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground=COLORS["accent"])
        style.configure("Value.TLabel", font=("Consolas", 12, "bold"), foreground=COLORS["text"])
        style.configure("Good.TLabel", font=("Consolas", 12, "bold"), foreground=COLORS["green"])
        style.configure("Bad.TLabel", font=("Consolas", 12, "bold"), foreground=COLORS["red"])
        style.configure("Dim.TLabel", font=("Segoe UI", 9), foreground=COLORS["text_dim"])

        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(15, 8))
        style.configure("Start.TButton", background=COLORS["green"], foreground="#1a1b26")
        style.configure("Stop.TButton", background=COLORS["red"], foreground="#1a1b26")
        style.configure("Warn.TButton", background=COLORS["yellow"], foreground="#1a1b26")

        style.configure("TNotebook", background=COLORS["bg"])
        style.configure("TNotebook.Tab", font=("Segoe UI", 10), padding=(12, 6),
                        background=COLORS["bg_tertiary"], foreground=COLORS["text_dim"])
        style.map("TNotebook.Tab", background=[("selected", COLORS["bg_secondary"])],
                  foreground=[("selected", COLORS["accent"])])

        style.configure("Treeview", background=COLORS["bg_secondary"], foreground=COLORS["text"],
                        fieldbackground=COLORS["bg_secondary"], font=("Consolas", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"),
                        background=COLORS["bg_tertiary"], foreground=COLORS["accent"])
        style.map("Treeview", background=[("selected", COLORS["bg_tertiary"])])

        style.configure("TLabelframe", background=COLORS["bg_secondary"], foreground=COLORS["accent"])
        style.configure("TLabelframe.Label", background=COLORS["bg_secondary"],
                        foreground=COLORS["accent"], font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        # Title bar
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        ttk.Label(title_frame, text="Kalshi Market Maker", style="Title.TLabel").pack(side=tk.LEFT)
        self.status_label = ttk.Label(title_frame, text="STOPPED", style="Bad.TLabel")
        self.status_label.pack(side=tk.RIGHT, padx=10)
        ttk.Label(title_frame, text="Status:", style="Dim.TLabel").pack(side=tk.RIGHT)

        # Control buttons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=15, pady=5)

        self.start_btn = ttk.Button(btn_frame, text="Start", style="Start.TButton", command=self._start_bot)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.pause_btn = ttk.Button(btn_frame, text="Pause", style="Warn.TButton", command=self._pause_bot, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="Stop", style="Stop.TButton", command=self._stop_bot, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        sep = ttk.Separator(btn_frame, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=3)

        self.emergency_btn = ttk.Button(btn_frame, text="EMERGENCY STOP", style="Stop.TButton", command=self._emergency_stop)
        self.emergency_btn.pack(side=tk.LEFT, padx=5)

        self.cancel_all_btn = ttk.Button(btn_frame, text="Cancel All Orders", command=self._cancel_all)
        self.cancel_all_btn.pack(side=tk.RIGHT, padx=5)

        # Stats row
        stats_frame = ttk.Frame(self.root)
        stats_frame.pack(fill=tk.X, padx=15, pady=5)

        self.stat_widgets = {}
        stat_defs = [
            ("balance", "Balance", "$0.00"),
            ("daily_pnl", "Daily P&L", "$0.00"),
            ("positions", "Positions", "0"),
            ("open_orders", "Open Orders", "0"),
            ("markets", "Markets", "0"),
            ("cycles", "Cycles", "0"),
        ]
        for key, label, default in stat_defs:
            card = ttk.Frame(stats_frame, style="Card.TFrame", padding=8)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
            ttk.Label(card, text=label, style="Dim.TLabel").pack()
            val_label = ttk.Label(card, text=default, style="Value.TLabel")
            val_label.pack()
            self.stat_widgets[key] = val_label

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 10))

        self._build_markets_tab()
        self._build_orders_tab()
        self._build_settings_tab()
        self._build_log_tab()

    def _build_markets_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="  Markets  ")

        cols = ("ticker", "title", "bid", "ask", "fair_value", "spread", "position", "volume", "expiry")
        self.markets_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        headers = {
            "ticker": ("Ticker", 110), "title": ("Title", 200), "bid": ("Bid", 60),
            "ask": ("Ask", 60), "fair_value": ("Fair Val", 70), "spread": ("Spread", 60),
            "position": ("Pos", 50), "volume": ("Vol", 60), "expiry": ("Hrs Left", 70),
        }
        for col, (heading, width) in headers.items():
            self.markets_tree.heading(col, text=heading)
            self.markets_tree.column(col, width=width, anchor=tk.CENTER if col != "title" else tk.W)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.markets_tree.yview)
        self.markets_tree.configure(yscrollcommand=scrollbar.set)
        self.markets_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_orders_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="  Orders  ")

        cols = ("order_id", "ticker", "side", "price", "size", "status", "age")
        self.orders_tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)

        headers = {
            "order_id": ("Order ID", 100), "ticker": ("Ticker", 110), "side": ("Side", 60),
            "price": ("Price", 60), "size": ("Size", 50), "status": ("Status", 80), "age": ("Age", 60),
        }
        for col, (heading, width) in headers.items():
            self.orders_tree.heading(col, text=heading)
            self.orders_tree.column(col, width=width, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=scrollbar.set)
        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_settings_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="  Settings  ")

        canvas = tk.Canvas(frame, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.setting_vars = {}

        # Environment
        env_frame = ttk.LabelFrame(scroll_frame, text="Environment", padding=10)
        env_frame.pack(fill=tk.X, padx=5, pady=5)
        self._add_checkbox(env_frame, "Demo Mode", "api.use_demo", self.config.api.use_demo)

        # Strategy
        strat_frame = ttk.LabelFrame(scroll_frame, text="Strategy", padding=10)
        strat_frame.pack(fill=tk.X, padx=5, pady=5)
        self._add_entry(strat_frame, "Min Spread (cents)", "strategy.min_spread_cents", self.config.strategy.min_spread_cents)
        self._add_entry(strat_frame, "Max Spread (cents)", "strategy.max_spread_cents", self.config.strategy.max_spread_cents)
        self._add_entry(strat_frame, "Order Size", "strategy.order_size", self.config.strategy.order_size)
        self._add_entry(strat_frame, "Max Order Size", "strategy.max_order_size", self.config.strategy.max_order_size)
        self._add_entry(strat_frame, "Inventory Risk Aversion", "strategy.inventory_risk_aversion", self.config.strategy.inventory_risk_aversion)
        self._add_entry(strat_frame, "Max Position", "strategy.max_position", self.config.strategy.max_position)
        self._add_entry(strat_frame, "Quote Refresh (sec)", "strategy.quote_refresh_seconds", self.config.strategy.quote_refresh_seconds)

        # Risk
        risk_frame = ttk.LabelFrame(scroll_frame, text="Risk Management", padding=10)
        risk_frame.pack(fill=tk.X, padx=5, pady=5)
        self._add_entry(risk_frame, "Max Daily Loss (cents)", "risk.max_daily_loss_cents", self.config.risk.max_daily_loss_cents)
        self._add_entry(risk_frame, "Kill Switch Loss (cents)", "risk.kill_switch_loss_cents", self.config.risk.kill_switch_loss_cents)
        self._add_entry(risk_frame, "Max Position Value (cents)", "risk.max_position_value_cents", self.config.risk.max_position_value_cents)
        self._add_entry(risk_frame, "Max Open Orders", "risk.max_open_orders", self.config.risk.max_open_orders)

        # Market Selection
        mkt_frame = ttk.LabelFrame(scroll_frame, text="Market Selection", padding=10)
        mkt_frame.pack(fill=tk.X, padx=5, pady=5)
        self._add_entry(mkt_frame, "Target Series (comma-sep)", "market.target_series", ",".join(self.config.market.target_series))
        self._add_entry(mkt_frame, "Max Hours to Close", "market.max_hours_to_expiry", self.config.market.max_hours_to_expiry)
        self._add_entry(mkt_frame, "Min Hours to Close", "market.min_hours_to_expiry", self.config.market.min_hours_to_expiry)
        self._add_entry(mkt_frame, "Max Active Markets", "market.max_active_markets", self.config.market.max_active_markets)
        self._add_entry(mkt_frame, "Max Markets Per Event", "market.max_markets_per_event", self.config.market.max_markets_per_event)
        self._add_entry(mkt_frame, "Min Price (cents)", "market.min_price_cents", self.config.market.min_price_cents)
        self._add_entry(mkt_frame, "Max Price (cents)", "market.max_price_cents", self.config.market.max_price_cents)

        # Save button
        save_btn = ttk.Button(scroll_frame, text="Save Settings", command=self._save_settings)
        save_btn.pack(pady=10)

    def _build_log_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="  Log  ")

        self.log_text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, font=("Consolas", 9),
            bg=COLORS["bg_secondary"], fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            height=20, state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Clear Log", command=self._clear_log).pack(side=tk.RIGHT)

    def _add_entry(self, parent, label, key, default):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=25).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(default))
        entry = ttk.Entry(row, textvariable=var, width=20)
        entry.pack(side=tk.LEFT, padx=5)
        self.setting_vars[key] = var

    def _add_checkbox(self, parent, label, key, default):
        var = tk.BooleanVar(value=default)
        cb = tk.Checkbutton(
            parent, text=label, variable=var,
            bg=COLORS["bg_secondary"], fg=COLORS["text"],
            selectcolor=COLORS["bg_tertiary"], activebackground=COLORS["bg_secondary"],
            font=("Segoe UI", 10),
        )
        cb.pack(anchor=tk.W, pady=2)
        self.setting_vars[key] = var

    # ── Actions ─────────────────────────────────────────────────
    def _start_bot(self):
        if not self.credentials.is_configured:
            messagebox.showerror("Error", "API key not configured. Run the setup wizard first.\n\n"
                                 "Use: ./start.sh --setup  (or start.bat --setup)")
            return

        self.engine = BotEngine(self.config, self.credentials)
        self.engine.set_callbacks(
            on_status=self._on_status_change,
            on_data=self._on_data_update,
            on_error=self._on_error,
        )

        if self.engine.start():
            self.start_btn.configure(state=tk.DISABLED)
            self.pause_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.NORMAL)
            self._schedule_update()
        else:
            messagebox.showerror("Error", f"Failed to start: {self.engine.last_error}")

    def _pause_bot(self):
        if self.engine:
            if self.engine.is_paused:
                self.engine.resume()
                self.pause_btn.configure(text="Pause")
            else:
                self.engine.pause()
                self.pause_btn.configure(text="Resume")

    def _stop_bot(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.start_btn.configure(state=tk.NORMAL)
        self.pause_btn.configure(state=tk.DISABLED, text="Pause")
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="STOPPED", style="Bad.TLabel")

    def _emergency_stop(self):
        if self.engine:
            self.engine.emergency_stop()
            self.engine = None
        self.start_btn.configure(state=tk.NORMAL)
        self.pause_btn.configure(state=tk.DISABLED, text="Pause")
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="EMERGENCY STOPPED", style="Bad.TLabel")
        messagebox.showwarning("Emergency Stop", "All orders cancelled. Bot stopped.")

    def _cancel_all(self):
        if self.engine:
            try:
                cancelled = self.engine.api.cancel_all_orders()
                messagebox.showinfo("Orders Cancelled", f"Cancelled {cancelled} orders")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _save_settings(self):
        try:
            # Apply settings from GUI vars to config
            for key, var in self.setting_vars.items():
                parts = key.split(".")
                obj = self.config
                for part in parts[:-1]:
                    obj = getattr(obj, part)
                attr = parts[-1]
                current = getattr(obj, attr)
                val = var.get()

                if isinstance(current, bool):
                    setattr(obj, attr, bool(val))
                elif isinstance(current, int):
                    setattr(obj, attr, int(float(val)))
                elif isinstance(current, float):
                    setattr(obj, attr, float(val))
                elif isinstance(current, list):
                    setattr(obj, attr, [s.strip() for s in val.split(",") if s.strip()])
                else:
                    setattr(obj, attr, val)

            self.config.api.set_environment(self.config.api.use_demo)
            self.config.save()
            messagebox.showinfo("Saved", "Settings saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── Updates ─────────────────────────────────────────────────
    def _schedule_update(self):
        if self.engine and self.engine.is_running:
            self._update_display()
            self._update_job = self.root.after(2000, self._schedule_update)

    def _update_display(self):
        if not self.engine:
            return

        try:
            summary = self.engine.get_status_summary()

            # Stats
            balance = summary.get("balance")
            if balance is not None:
                self.stat_widgets["balance"].configure(text=f"${balance / 100:.2f}")

            pnl = summary.get("daily_pnl", 0)
            pnl_text = f"${pnl / 100:+.2f}"
            pnl_style = "Good.TLabel" if pnl >= 0 else "Bad.TLabel"
            self.stat_widgets["daily_pnl"].configure(text=pnl_text, style=pnl_style)

            self.stat_widgets["positions"].configure(text=str(summary.get("total_positions", 0)))
            self.stat_widgets["open_orders"].configure(text=str(summary.get("open_orders", 0)))
            self.stat_widgets["markets"].configure(text=str(summary.get("active_markets", 0)))
            self.stat_widgets["cycles"].configure(text=str(summary.get("cycle", 0)))

            # Markets table
            self.markets_tree.delete(*self.markets_tree.get_children())
            for ticker, data in summary.get("positions", {}).items():
                values = (
                    ticker,
                    data.get("title", "")[:35],
                    f"{data['bid']}c" if data.get("bid") else "-",
                    f"{data['ask']}c" if data.get("ask") else "-",
                    f"{data['fair_value']}" if data.get("fair_value") else "-",
                    f"{data['spread']}" if data.get("spread") else "-",
                    str(data.get("position", 0)),
                    str(data.get("volume", 0)),
                    f"{data['hours_to_expiry']}h" if data.get("hours_to_expiry") else "-",
                )
                self.markets_tree.insert("", tk.END, values=values)

            # Orders table
            self.orders_tree.delete(*self.orders_tree.get_children())
            for order in self.engine.order_manager.get_active_orders():
                age = int(time.time() - order.created_at)
                values = (
                    order.order_id[:12],
                    order.ticker,
                    "BID" if order.is_bid else "ASK",
                    f"{order.price}c",
                    str(order.size),
                    order.status,
                    f"{age}s",
                )
                self.orders_tree.insert("", tk.END, values=values)

        except Exception as e:
            logger.error("Display update error: %s", e)

    def _on_status_change(self, status: str):
        def update():
            status_map = {
                "running": ("RUNNING", "Good.TLabel"),
                "paused": ("PAUSED", "Value.TLabel"),
                "stopped": ("STOPPED", "Bad.TLabel"),
                "emergency_stopped": ("EMERGENCY STOPPED", "Bad.TLabel"),
            }
            text, style = status_map.get(status, (status.upper(), "Value.TLabel"))
            self.status_label.configure(text=text, style=style)
        self.root.after(0, update)

    def _on_data_update(self):
        pass  # Handled by periodic _schedule_update

    def _on_error(self, error: str):
        def update():
            self._append_log(f"ERROR: {error}")
        self.root.after(0, update)

    def _append_log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _setup_log_handler(self):
        class GUILogHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            def emit(self, record):
                try:
                    msg = self.format(record)
                    self.callback(msg)
                except Exception:
                    pass

        handler = GUILogHandler(lambda msg: self.root.after(0, self._append_log, msg))
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        handler.setLevel(logging.INFO)
        logging.getLogger("kalshi_bot").addHandler(handler)

    def _on_close(self):
        if self.engine and self.engine.is_running:
            if messagebox.askyesno("Quit", "Bot is running. Stop and quit?"):
                self.engine.stop()
            else:
                return
        if self._update_job:
            self.root.after_cancel(self._update_job)
        self.root.destroy()

    def run(self):
        self.root.mainloop()
