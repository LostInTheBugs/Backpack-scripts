CREATE TABLE bot_signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT,              -- Ex: RANGE, BULL, BEAR
    strategy TEXT,            -- Ex: Range, Auto, Combo, etc.
    signal TEXT,              -- BUY, SELL, HOLD
    price NUMERIC(18,8),
    rsi NUMERIC(6,2),
    trix NUMERIC(8,4),
    note TEXT                 -- Eventuel commentaire ou log
);

