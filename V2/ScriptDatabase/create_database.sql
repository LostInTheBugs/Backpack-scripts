CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    market_type TEXT,
    strategy TEXT,
    signal TEXT,
    price FLOAT,
    rsi FLOAT,
    trix FLOAT,
    raw_data JSONB
);