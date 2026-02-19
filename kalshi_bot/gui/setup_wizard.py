"""Setup wizard - guides users through initial configuration."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Optional

from kalshi_bot.core.config import BotConfig, Credentials, ApiConfig

COLORS = {
    "bg": "#1a1b26",
    "bg_secondary": "#24283b",
    "text": "#c0caf5",
    "text_dim": "#565f89",
    "accent": "#7aa2f7",
    "green": "#9ece6a",
    "red": "#f7768e",
    "border": "#3b4261",
}


class SetupWizard:
    """Multi-step setup wizard for first-time configuration."""

    def __init__(self, parent: Optional[tk.Tk] = None):
        self.config = BotConfig.load()
        self.credentials = Credentials.load()
        self.completed = False
        self.current_step = 0

        if parent:
            self.root = tk.Toplevel(parent)
        else:
            self.root = tk.Tk()
        self.root.title("Kalshi Bot - Setup Wizard")
        self.root.geometry("650x560")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS["bg"])

        self._setup_styles()
        self._build_ui()
        self._show_step(0)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 11))
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=COLORS["accent"])
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground=COLORS["text_dim"])
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(15, 8))
        style.configure("Accent.TButton", background=COLORS["accent"])

    def _build_ui(self):
        self.progress_frame = ttk.Frame(self.root)
        self.progress_frame.pack(fill=tk.X, padx=30, pady=(20, 10))

        self.step_labels = []
        steps = ["Welcome", "API Key", "Environment", "Strategy", "Done"]
        for i, step_name in enumerate(steps):
            lbl = ttk.Label(self.progress_frame, text=f"{i+1}. {step_name}", style="Sub.TLabel")
            lbl.pack(side=tk.LEFT, padx=8)
            self.step_labels.append(lbl)

        ttk.Separator(self.root).pack(fill=tk.X, padx=20, pady=5)

        self.content_frame = ttk.Frame(self.root)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=10)

        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill=tk.X, padx=30, pady=(5, 20))

        self.back_btn = ttk.Button(nav_frame, text="Back", command=self._prev_step)
        self.back_btn.pack(side=tk.LEFT)
        self.next_btn = ttk.Button(nav_frame, text="Next", style="Accent.TButton", command=self._next_step)
        self.next_btn.pack(side=tk.RIGHT)

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _update_progress(self):
        for i, lbl in enumerate(self.step_labels):
            if i == self.current_step:
                lbl.configure(foreground=COLORS["accent"], font=("Segoe UI", 10, "bold"))
            elif i < self.current_step:
                lbl.configure(foreground=COLORS["green"], font=("Segoe UI", 10))
            else:
                lbl.configure(foreground=COLORS["text_dim"], font=("Segoe UI", 10))

    def _show_step(self, step: int):
        self.current_step = step
        self._clear_content()
        self._update_progress()

        self.back_btn.configure(state=tk.NORMAL if step > 0 else tk.DISABLED)
        self.next_btn.configure(text="Finish" if step == 4 else "Next")

        builders = [
            self._build_welcome,
            self._build_credentials,
            self._build_environment,
            self._build_strategy,
            self._build_done,
        ]
        builders[step]()

    # ── Step 0: Welcome ─────────────────────────────────────
    def _build_welcome(self):
        ttk.Label(self.content_frame, text="Welcome to Kalshi Market Maker",
                  style="Header.TLabel").pack(pady=(10, 20))

        info = (
            "This wizard will help you configure the bot.\n\n"
            "You will need:\n"
            "  1. A Kalshi account (demo or live)\n"
            "  2. An API key from your Kalshi account settings\n\n"
            "To create an API key:\n"
            "  1. Log in to kalshi.com\n"
            "  2. Go to Settings > API Keys\n"
            "  3. Click 'Create API Key'\n"
            "  4. Download the private key (.pem file)\n"
            "  5. Copy the Key ID shown on the page\n\n"
            "We recommend starting in DEMO mode to test\n"
            "before switching to live trading."
        )
        ttk.Label(self.content_frame, text=info, justify=tk.LEFT,
                  wraplength=540).pack(anchor=tk.W)

    # ── Step 1: API Key ─────────────────────────────────────
    def _build_credentials(self):
        ttk.Label(self.content_frame, text="Kalshi API Key",
                  style="Header.TLabel").pack(pady=(10, 5))
        ttk.Label(self.content_frame, text="From kalshi.com > Settings > API Keys. Stored locally, never shared.",
                  style="Sub.TLabel").pack(pady=(0, 15))

        form = ttk.Frame(self.content_frame)
        form.pack(fill=tk.X)

        # API Key ID
        ttk.Label(form, text="API Key ID:").grid(row=0, column=0, sticky=tk.W, pady=8)
        self.key_id_var = tk.StringVar(value=self.credentials.api_key_id)
        key_entry = ttk.Entry(form, textvariable=self.key_id_var, width=44, font=("Consolas", 10))
        key_entry.grid(row=0, column=1, columnspan=2, padx=10, pady=8, sticky=tk.W)

        # Private Key File
        ttk.Label(form, text="Private Key:").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.key_path_var = tk.StringVar(value=self.credentials.private_key_path)
        path_entry = ttk.Entry(form, textvariable=self.key_path_var, width=34, font=("Consolas", 10))
        path_entry.grid(row=1, column=1, padx=(10, 5), pady=8, sticky=tk.W)
        browse_btn = ttk.Button(form, text="Browse", command=self._browse_key_file)
        browse_btn.grid(row=1, column=2, pady=8)

        self.key_status_label = ttk.Label(form, text="", style="Sub.TLabel")
        self.key_status_label.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=10)
        self._update_key_status()

        # Test connection button
        test_frame = ttk.Frame(self.content_frame)
        test_frame.pack(fill=tk.X, pady=15)
        self.test_btn = ttk.Button(test_frame, text="Test Connection", command=self._test_connection)
        self.test_btn.pack(side=tk.LEFT)
        self.test_result = ttk.Label(test_frame, text="", style="Sub.TLabel")
        self.test_result.pack(side=tk.LEFT, padx=10)

        # Help text
        ttk.Label(self.content_frame, text=(
            "How to get your API key:\n"
            "  1. Log in at kalshi.com (or demo portal)\n"
            "  2. Go to Settings > API Keys\n"
            "  3. Click 'Create API Key'\n"
            "  4. Save the .pem file somewhere safe\n"
            "  5. Copy the Key ID and paste it above"
        ), style="Sub.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=(10, 0))

    def _browse_key_file(self):
        path = filedialog.askopenfilename(
            title="Select Private Key File",
            filetypes=[("PEM files", "*.pem"), ("Key files", "*.key"), ("All files", "*.*")],
        )
        if path:
            self.key_path_var.set(path)
            self._update_key_status()

    def _update_key_status(self):
        path = self.key_path_var.get().strip()
        if not path:
            return
        p = Path(path)
        if not p.exists():
            self.key_status_label.configure(text="File not found", foreground=COLORS["red"])
        elif p.stat().st_size < 100:
            self.key_status_label.configure(text="File seems too small", foreground=COLORS["red"])
        else:
            self.key_status_label.configure(text="Key file found", foreground=COLORS["green"])

    # ── Step 2: Environment ──────────────────────────────────
    def _build_environment(self):
        ttk.Label(self.content_frame, text="Trading Environment",
                  style="Header.TLabel").pack(pady=(10, 15))

        self.demo_var = tk.BooleanVar(value=self.config.api.use_demo)

        demo_frame = ttk.Frame(self.content_frame)
        demo_frame.pack(fill=tk.X, pady=5)
        demo_rb = tk.Radiobutton(
            demo_frame, text="Demo Mode (Paper Trading)", variable=self.demo_var, value=True,
            bg=COLORS["bg"], fg=COLORS["green"], selectcolor=COLORS["bg_secondary"],
            font=("Segoe UI", 12, "bold"), activebackground=COLORS["bg"],
        )
        demo_rb.pack(anchor=tk.W)
        ttk.Label(demo_frame, text="    Trade with fake money on Kalshi's demo exchange.\n"
                  "    Recommended for testing.", style="Sub.TLabel").pack(anchor=tk.W)

        live_frame = ttk.Frame(self.content_frame)
        live_frame.pack(fill=tk.X, pady=(15, 5))
        live_rb = tk.Radiobutton(
            live_frame, text="Live Mode (Real Money)", variable=self.demo_var, value=False,
            bg=COLORS["bg"], fg=COLORS["red"], selectcolor=COLORS["bg_secondary"],
            font=("Segoe UI", 12, "bold"), activebackground=COLORS["bg"],
        )
        live_rb.pack(anchor=tk.W)
        ttk.Label(live_frame, text="    Trade with real money. Use with caution.\n"
                  "    Make sure risk limits are set appropriately.", style="Sub.TLabel").pack(anchor=tk.W)

    # ── Step 3: Strategy ──────────────────────────────────────
    def _build_strategy(self):
        ttk.Label(self.content_frame, text="Strategy Configuration",
                  style="Header.TLabel").pack(pady=(10, 5))
        ttk.Label(self.content_frame, text="Fine-tune these later in Settings.",
                  style="Sub.TLabel").pack(pady=(0, 10))

        form = ttk.Frame(self.content_frame)
        form.pack(fill=tk.X)

        self.strat_vars = {}
        fields = [
            ("Order Size (contracts)", "order_size", self.config.strategy.order_size),
            ("Min Spread (cents)", "min_spread_cents", self.config.strategy.min_spread_cents),
            ("Max Position (contracts)", "max_position", self.config.strategy.max_position),
            ("Max Daily Loss (cents)", "max_daily_loss", self.config.risk.max_daily_loss_cents),
            ("Target Series", "target_series", ",".join(self.config.market.target_series)),
        ]

        for i, (label, key, default) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky=tk.W, pady=5)
            var = tk.StringVar(value=str(default))
            entry = ttk.Entry(form, textvariable=var, width=20, font=("Consolas", 11))
            entry.grid(row=i, column=1, padx=10, pady=5)
            self.strat_vars[key] = var

        ttk.Label(self.content_frame, text=(
            "\nRecommended series for market making:\n"
            "  KXHIGHNY - NYC Daily High Temperature\n"
            "  KXLOWNY  - NYC Daily Low Temperature\n"
            "  KXHIGHCHI - Chicago Daily High Temperature\n"
            "  KXRAIN   - Daily Rainfall"
        ), style="Sub.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=10)

    # ── Step 4: Done ──────────────────────────────────────────
    def _build_done(self):
        ttk.Label(self.content_frame, text="Setup Complete!",
                  style="Header.TLabel").pack(pady=(20, 15))

        key_display = self.credentials.api_key_id
        if len(key_display) > 16:
            key_display = key_display[:8] + "..." + key_display[-4:]

        summary = (
            f"Environment: {'Demo' if self.config.api.use_demo else 'LIVE'}\n"
            f"API Key: {key_display}\n"
            f"Private Key: {Path(self.credentials.private_key_path).name}\n"
            f"Order Size: {self.config.strategy.order_size}\n"
            f"Min Spread: {self.config.strategy.min_spread_cents}c\n"
            f"Max Position: {self.config.strategy.max_position}\n"
            f"Max Daily Loss: ${self.config.risk.max_daily_loss_cents / 100:.2f}\n"
            f"Target Series: {', '.join(self.config.market.target_series)}\n"
        )
        ttk.Label(self.content_frame, text=summary, font=("Consolas", 11),
                  justify=tk.LEFT).pack(anchor=tk.W, padx=20)

        ttk.Label(self.content_frame, text=(
            "\nClick 'Finish' to save and launch the control panel.\n"
            "You can adjust all settings later from the Settings tab."
        ), style="Sub.TLabel").pack(pady=15)

    # ── Connection Test ───────────────────────────────────────
    def _test_connection(self):
        from kalshi_bot.core.api import KalshiApiClient

        key_id = self.key_id_var.get().strip()
        key_path = self.key_path_var.get().strip()
        if not key_id or not key_path:
            self.test_result.configure(text="Enter API Key ID and select private key file", foreground=COLORS["red"])
            return

        if not Path(key_path).exists():
            self.test_result.configure(text="Private key file not found", foreground=COLORS["red"])
            return

        self.test_result.configure(text="Testing...", foreground=COLORS["text_dim"])
        self.root.update()

        test_creds = Credentials(api_key_id=key_id, private_key_path=key_path)
        test_config = ApiConfig()
        test_config.set_environment(self.config.api.use_demo)
        client = KalshiApiClient(test_config, test_creds)

        if client.login():
            balance = client.get_balance()
            env = "demo" if self.config.api.use_demo else "live"
            bal_str = f"${balance / 100:.2f}" if balance is not None else "N/A"
            self.test_result.configure(
                text=f"Connected ({env})! Balance: {bal_str}",
                foreground=COLORS["green"],
            )
        else:
            self.test_result.configure(
                text="Connection failed - check API key ID and .pem file",
                foreground=COLORS["red"],
            )

    # ── Navigation ────────────────────────────────────────────
    def _next_step(self):
        if not self._validate_step():
            return

        if self.current_step == 4:
            self._finish()
            return

        self._save_step()
        self._show_step(self.current_step + 1)

    def _prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _validate_step(self) -> bool:
        if self.current_step == 1:
            key_id = self.key_id_var.get().strip()
            key_path = self.key_path_var.get().strip()
            if not key_id:
                messagebox.showwarning("Missing Info", "Please enter your API Key ID.")
                return False
            if not key_path:
                messagebox.showwarning("Missing Info", "Please select your private key (.pem) file.")
                return False
            if not Path(key_path).exists():
                messagebox.showwarning("File Not Found", f"Private key file not found:\n{key_path}")
                return False
        return True

    def _save_step(self):
        if self.current_step == 1:
            self.credentials.api_key_id = self.key_id_var.get().strip()
            self.credentials.private_key_path = self.key_path_var.get().strip()

        elif self.current_step == 2:
            self.config.api.set_environment(self.demo_var.get())

        elif self.current_step == 3:
            try:
                self.config.strategy.order_size = int(self.strat_vars["order_size"].get())
                self.config.strategy.min_spread_cents = int(self.strat_vars["min_spread_cents"].get())
                self.config.strategy.max_position = int(self.strat_vars["max_position"].get())
                self.config.risk.max_daily_loss_cents = int(self.strat_vars["max_daily_loss"].get())
                series = self.strat_vars["target_series"].get()
                self.config.market.target_series = [s.strip() for s in series.split(",") if s.strip()]
            except ValueError:
                messagebox.showwarning("Invalid Input", "Please enter valid numbers.")

    def _finish(self):
        self.credentials.save()
        self.config.save()
        self.completed = True
        self.root.destroy()

    def run(self) -> bool:
        self.root.mainloop()
        return self.completed
