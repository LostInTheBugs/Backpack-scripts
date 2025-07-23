CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE ohlcv_btc__usdc__perp (
    symbol TEXT NOT NULL,
    interval_sec INTEGER NOT NULL, -- granularité (1, 10, 60, ...)
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    PRIMARY KEY (symbol, interval_sec, timestamp)
);
SELECT create_hypertable('ohlcv_btc__usdc__perp', 'timestamp');

CREATE TABLE ohlcv_eth__usdc__perp (
    symbol TEXT NOT NULL,
    interval_sec INTEGER NOT NULL, -- granularité (1, 10, 60, ...)
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    PRIMARY KEY (symbol, interval_sec, timestamp)
);
SELECT create_hypertable('ohlcv_eth__usdc__perp', 'timestamp');

CREATE TABLE ohlcv_sol__sol__perp (
    symbol TEXT NOT NULL,
    interval_sec INTEGER NOT NULL, -- granularité (1, 10, 60, ...)
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    PRIMARY KEY (symbol, interval_sec, timestamp)
);
SELECT create_hypertable('ohlcv_sol__usdc__perp', 'timestamp');

CREATE TABLE ohlcv_sui__usdc__perp (
    symbol TEXT NOT NULL,
    interval_sec INTEGER NOT NULL, -- granularité (1, 10, 60, ...)
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    PRIMARY KEY (symbol, interval_sec, timestamp)
);
SELECT create_hypertable('ohlcv_sui__usdc__perp', 'timestamp');