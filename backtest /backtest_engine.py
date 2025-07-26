import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, timezone
from signals.macd_rsi_breakout import get_combined_signal
from utils.logger import log
from utils.ohlcv_utils import get_ohlcv_df

# Format table name same as in main script
def format_table_name(symbol: str) -> str:
    parts = symbol.lower().split("_")
    return "ohlcv_" + "__".join(parts)

async def fetch_ohlcv(pool, symbol):
    table_name = format_table_name(symbol)
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM {table_name} ORDER BY timestamp ASC")
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # Convert timestamps if needed
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        return df

async def run_backtest_async(symbol, interval, dsn):
    pool = await asyncpg.create_pool(dsn=dsn)

    log(f"[{symbol}] 🧪 Chargement données pour backtest {interval}")

    df = await fetch_ohlcv(pool, symbol)
    if df.empty:
        log(f"[{symbol}] ❌ Pas de données pour le backtest")
        await pool.close()
        return

    # Ici tu peux filtrer ou resampler selon interval si besoin
    # Pour simplifier on prend tout tel quel

    # Calcul des signaux (on doit reproduire le même calcul que dans le bot)
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    signal = get_combined_signal(df)

    # Simulation simple : on compte combien de BUY/SELL détectés
    signals = df.apply(lambda row: get_combined_signal(df), axis=1)  # ou appliquer sur chaque ligne si possible

    # Pour simplifier, on affiche le signal final (à améliorer)
    log(f"[{symbol}] 🎯 Signal final backtest: {signal}")

    await pool.close()

def run_backtest(symbol, interval):
    import os
    dsn = os.environ.get("PG_DSN")
    if not dsn:
        print("⚠️ PG_DSN non défini dans les variables d'environnement")
        return
    asyncio.run(run_backtest_async(symbol, interval, dsn))
