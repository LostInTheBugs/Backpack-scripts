import asyncio
import asyncpg
import pandas as pd
import os
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal

async def fetch_ohlcv_from_db(pool, symbol, interval):
    """
    Récupère les données OHLCV depuis la base PostgreSQL pour un symbole et interval donné.
    interval: '1s', '1m', '1h', '1d', etc.
    """
    table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                ORDER BY timestamp ASC
            """)
            if not rows:
                log(f"[{symbol}] ❌ Pas de données OHLCV en base pour backtest")
                return pd.DataFrame()
            data = [dict(row) for row in rows]
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('UTC')
            return df
        except Exception as e:
            log(f"[{symbol}] ❌ Erreur fetch OHLCV backtest: {e}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, interval: str, dsn: str):
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        async with pool.acquire() as conn:
            table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))
            interval_map = {'1s': 1, '1m': 60, '1h': 3600, '1d': 86400}
            interval_sec = interval_map.get(interval, 1)
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                WHERE interval_sec = $1
                ORDER BY timestamp
            """
            rows = await conn.fetch(query, interval_sec)
            if not rows:
                print(f"[{symbol}] ❌ Pas de données OHLCV pour le backtest avec intervalle {interval} ({interval_sec}s)")
                return
            data = [dict(row) for row in rows]
            df = pd.DataFrame(data)
            if 'timestamp' not in df.columns:
                print(f"[{symbol}] ❌ La colonne 'timestamp' est absente dans les données")
                return
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('UTC')
            df.set_index('timestamp', inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Resample avec fréquence corrigée 'h' au lieu de 'H'
            freq = interval.lower()
            df_resampled = df.resample(freq).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
            }).dropna()

            print(f"[{symbol}] ✅ Données OHLCV chargées ({len(df_resampled)} lignes), début: {df_resampled.index.min()}, fin: {df_resampled.index.max()}")

            signal = get_combined_signal(df_resampled)
            print(f"[{symbol}] Backtest signal final: {signal}")

        await pool.close()

    except Exception as e:
        print(f"[{symbol}] 💥 Exception durant le backtest: {e}")
        traceback.print_exc()

async def backtest_symbol(symbol: str, interval: str):
    try:
        from backtest.backtest_engine import run_backtest_async
        log(f"[{symbol}] 🧪 Lancement du backtest en {interval}")
        dsn = os.environ.get("PG_DSN")
        await run_backtest_async(symbol, interval, dsn)
    except ModuleNotFoundError:
        log(f"[{symbol}] ❌ Module backtest non trouvé. Veuillez créer backtest/backtest_engine.py")
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur durant le backtest: {e}")
        import traceback
        traceback.print_exc()

def run_backtest(symbol, interval):
    dsn = os.environ.get("PG_DSN")
    import asyncio
    asyncio.run(run_backtest_async(symbol, interval, dsn))
