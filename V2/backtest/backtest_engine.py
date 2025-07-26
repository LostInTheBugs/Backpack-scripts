import asyncio
import asyncpg
import pandas as pd
import os
from datetime import datetime, timezone
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal

def interval_to_pandas_freq(interval: str) -> str:
    """
    Convertit l'intervalle sous forme '1s', '2s', '1m', '5m', '1h', '1d' en fréquence pandas (resample).
    """
    unit = interval[-1]
    qty = int(interval[:-1])
    if unit == 's':
        return f"{qty}S"
    elif unit == 'm':
        return f"{qty}T"  # T = minutes
    elif unit == 'h':
        return f"{qty}h"
    elif unit == 'd':
        return f"{qty}D"
    else:
        return "1S"  # défaut

async def fetch_ohlcv_from_db(pool, symbol, interval):
    """
    Récupère les données OHLCV en 1 seconde (interval_sec=1) depuis la base PostgreSQL,
    puis fait un resampling dynamique sur l'interval demandé.
    """
    table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))

    async with pool.acquire() as conn:
        try:
            # Toujours récupérer en interval_sec=1 pour resampler ensuite
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

            data = [dict(row) for row in rows]
            df = pd.DataFrame(data)

            # Gestion timezone: tz naive -> localize Europe/Paris (ajuster selon ta zone)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('Europe/Paris').dt.tz_convert('UTC')
            else:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')

            df.set_index('timestamp', inplace=True)

            # Conversion colonnes en float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Resample selon intervalle demandé
            freq = interval_to_pandas_freq(interval)
            if freq != "1S":
                df_resampled = df.resample(freq).agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
            else:
                df_resampled = df

            return df_resampled

        except Exception as e:
            log(f"[{symbol}] ❌ Erreur fetch OHLCV backtest: {e}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, interval: str, dsn: str):
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        df = await fetch_ohlcv_from_db(pool, symbol, interval)

        if df.empty:
            print(f"[{symbol}] ❌ Pas de données OHLCV pour backtest avec intervalle {interval}")
            await pool.close()
            return

        print(f"[{symbol}] ✅ Données OHLCV chargées ({len(df)} lignes), début: {df.index.min()}, fin: {df.index.max()}")

        # Importer ta fonction signal ici (ou en début de fichier)
        signal = get_combined_signal(df)
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
    """
    Fonction synchrone qui peut être appelée hors boucle asyncio.
    """
    dsn = os.environ.get("PG_DSN")
    import asyncio
    asyncio.run(run_backtest_async(symbol, interval, dsn))

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
        traceback.print_exc()