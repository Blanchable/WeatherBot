-- Kalshi Weather Bot — SQLite schema

CREATE TABLE IF NOT EXISTS forecasts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id         TEXT    NOT NULL,
    fetched_at_utc  TEXT    NOT NULL,
    forecast_date   TEXT    NOT NULL,
    predicted_high  REAL,
    predicted_low   REAL,
    sigma           REAL,
    hourly_json     TEXT,
    raw_json        TEXT,
    UNIQUE(city_id, fetched_at_utc, forecast_date)
);

CREATE TABLE IF NOT EXISTS weather_markets (
    ticker          TEXT PRIMARY KEY,
    event_ticker    TEXT,
    city            TEXT    NOT NULL,
    market_date     TEXT    NOT NULL,
    market_type     TEXT    NOT NULL,  -- 'high_temp', 'low_temp', 'rain'
    strike_low      REAL,
    strike_high     REAL,
    strike_op       TEXT,  -- 'range', 'gte', 'lte'
    close_time      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'open',
    last_updated    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    ticker          TEXT    NOT NULL,
    side            TEXT    NOT NULL,   -- 'yes', 'no'
    action          TEXT    NOT NULL,   -- 'buy', 'sell'
    price_cents     INTEGER NOT NULL,
    quantity        INTEGER NOT NULL,
    filled_qty      INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'resting',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    is_paper        INTEGER NOT NULL DEFAULT 1,
    model_prob      REAL,
    model_ev        REAL,
    FOREIGN KEY (ticker) REFERENCES weather_markets(ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    side            TEXT    NOT NULL,   -- 'yes', 'no'
    quantity        INTEGER NOT NULL DEFAULT 0,
    avg_price_cents REAL    NOT NULL DEFAULT 0,
    unrealized_pnl  REAL    NOT NULL DEFAULT 0,
    realized_pnl    REAL    NOT NULL DEFAULT 0,
    opened_at       TEXT    NOT NULL,
    last_updated    TEXT    NOT NULL,
    is_paper        INTEGER NOT NULL DEFAULT 1,
    UNIQUE(ticker, side, is_paper)
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id         TEXT PRIMARY KEY,
    order_id        TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    price_cents     INTEGER NOT NULL,
    quantity        INTEGER NOT NULL,
    fee_dollars     REAL    NOT NULL DEFAULT 0,
    filled_at       TEXT    NOT NULL,
    is_paper        INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date_utc        TEXT PRIMARY KEY,
    realized_pnl    REAL    NOT NULL DEFAULT 0,
    fees_paid       REAL    NOT NULL DEFAULT 0,
    num_trades      INTEGER NOT NULL DEFAULT 0,
    num_markets     INTEGER NOT NULL DEFAULT 0,
    is_paper        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bot_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forecasts_city_date ON forecasts(city_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);
CREATE INDEX IF NOT EXISTS idx_fills_ticker ON fills(ticker);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
