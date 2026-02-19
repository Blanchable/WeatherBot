PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS forecast_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    forecast_valid_from_utc TEXT NOT NULL,
    confidence_spread_f REAL NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forecast_city_fetched
    ON forecast_snapshots(city_id, fetched_at_utc DESC);

CREATE TABLE IF NOT EXISTS market_meta (
    ticker TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    target_date TEXT NOT NULL,
    strike_type TEXT NOT NULL,
    strike_low REAL,
    strike_high REAL,
    close_time_utc TEXT NOT NULL,
    title TEXT NOT NULL,
    subtitle TEXT NOT NULL,
    volume_24h INTEGER NOT NULL DEFAULT 0,
    open_interest INTEGER NOT NULL DEFAULT 0,
    yes_bid INTEGER,
    yes_ask INTEGER,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    city_id TEXT NOT NULL,
    side TEXT NOT NULL,
    action TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    contracts INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_status_created
    ON orders(status, created_at_utc DESC);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    city_id TEXT NOT NULL,
    side TEXT NOT NULL,
    action TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    contracts INTEGER NOT NULL,
    mode TEXT NOT NULL,
    filled_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    contracts INTEGER NOT NULL,
    avg_price_cents INTEGER NOT NULL,
    realized_pnl_dollars REAL NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pnl_daily (
    trading_day TEXT PRIMARY KEY,
    realized_pnl_dollars REAL NOT NULL DEFAULT 0,
    unrealized_pnl_dollars REAL NOT NULL DEFAULT 0,
    fees_dollars REAL NOT NULL DEFAULT 0,
    gross_exposure_dollars REAL NOT NULL DEFAULT 0,
    net_exposure_dollars REAL NOT NULL DEFAULT 0,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_params (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);
