import asyncio
import asyncpg
import pandas as pd
import os
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal  # À adapter selon stratégie

async def fetch_ohlcv_from_db(pool, symbol):
    table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))
    async with pool.acquire() as conn:
        try:
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                WHERE interval_sec = 1
                ORDER BY timestamp ASC
            """
            rows = await conn.fetch(query)
            if not rows:
                log(f"[{symbol}] ❌ Pas de données OHLCV en base pour backtest")
                return pd.DataFrame()
            df = pd.DataFrame([dict(row) for row in rows])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('Europe/Paris').dt.tz_convert('UTC')
            else:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            df.set_index('timestamp', inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        except Exception as e:
            log(f"[{symbol}] ❌ Erreur fetch OHLCV backtest: {e}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, dsn: str, hours: int):
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        df = await fetch_ohlcv_from_db(pool, symbol)
        if df.empty:
            print(f"[{symbol}] ❌ Pas de données OHLCV pour backtest")
            await pool.close()
            return
        
        # Filtrer sur la fenêtre backtest : dernière date - heures
        end_time = df.index.max()
        start_time = end_time - pd.Timedelta(hours=hours)
        df_filtered = df.loc[(df.index >= start_time) & (df.index <= end_time)]
        
        print(f"[{symbol}] ✅ Données filtrées backtest {hours}h: {len(df_filtered)} lignes, début: {df_filtered.index.min()}, fin: {df_filtered.index.max()}")

        # Appeler la fonction signal sans resampling
        signal = get_combined_signal(df_filtered)
        print(f"[{symbol}] Backtest signal final: {signal}")

        await pool.close()

    except Exception as e:
        print(f"[{symbol}] 💥 Exception durant le backtest: {e}")
        traceback.print_exc()

async def backtest_symbol(symbol: str, hours: int):
    dsn = os.environ.get("PG_DSN")
    await run_backtest_async(symbol, dsn, hours)

def run_backtest(symbol, hours):
    dsn = os.environ.get("PG_DSN")
    asyncio.run(run_backtest_async(symbol, dsn, hours))
