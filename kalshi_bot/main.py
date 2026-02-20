"""Main entry point for the Kalshi Market Making Bot."""

import argparse
import logging
import sys

from kalshi_bot.core.config import BotConfig, Credentials, CONFIG_DIR


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def run_setup_wizard():
    from kalshi_bot.gui.setup_wizard import SetupWizard
    wizard = SetupWizard()
    return wizard.run()


def run_control_panel():
    from kalshi_bot.gui.control_panel import ControlPanel
    config = BotConfig.load()
    credentials = Credentials.load()
    panel = ControlPanel(config, credentials)
    panel.run()


def main():
    parser = argparse.ArgumentParser(description="Kalshi Market Making Bot")
    parser.add_argument("--setup", action="store_true", help="Run the setup wizard")
    parser.add_argument("--headless", action="store_true", help="Run without GUI (headless mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    credentials = Credentials.load()
    config = BotConfig.load()

    if args.setup or not credentials.is_configured:
        print("Starting setup wizard...")
        if not run_setup_wizard():
            print("Setup cancelled.")
            sys.exit(1)
        credentials = Credentials.load()
        config = BotConfig.load()

    if args.headless:
        run_headless(config, credentials)
    else:
        run_control_panel()


def run_headless(config: BotConfig, credentials: Credentials):
    """Run the bot without a GUI."""
    import signal
    import time
    from kalshi_bot.core.engine import BotEngine

    logger = logging.getLogger("kalshi_bot.headless")

    engine = BotEngine(config, credentials)
    engine.set_callbacks(
        on_error=lambda e: logger.error("Bot error: %s", e),
    )

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        logger.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting bot in headless mode...")
    if not engine.start():
        logger.error("Failed to start: %s", engine.last_error)
        sys.exit(1)

    try:
        while running and engine.is_running:
            summary = engine.get_status_summary()
            balance = summary.get("balance")
            pnl = summary.get("daily_pnl", 0)
            bal_str = f"${balance / 100:.2f}" if balance else "N/A"
            logger.info(
                "Cycle %d | Balance: %s | P&L: $%+.2f | Markets: %d | Orders: %d | Positions: %d",
                summary.get("cycle", 0),
                bal_str,
                pnl / 100,
                summary.get("active_markets", 0),
                summary.get("open_orders", 0),
                summary.get("total_positions", 0),
            )
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        engine.stop()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
