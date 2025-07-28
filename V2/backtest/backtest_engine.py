import asyncio
import asyncpg
import pandas as pd
import os
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal  # À ajuster selon la stratégie choisie
from pandas.tseries.frequencies import to_offset


async def fetch_ohlcv_from_db(pool, symbol):
    """
    Récupère les données OHLCV brutes à la seconde depuis PostgreSQL sans resample.
    """
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

            # Gestion timezone (UTC)
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('Europe/Paris').dt.tz_convert('UTC')
            else:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')

            df.set_index('timestamp', inplace=True)

            # Conversion colonnes numériques
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

        except Exception as e:
            log(f"[{symbol}] ❌ Erreur fetch OHLCV backtest: {e}")
            traceback.print_exc()
            return pd.DataFrame()


async def run_backtest_async(symbol: str, interval: str, dsn: str):
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        df = await fetch_ohlcv_from_db(pool, symbol)

        if df.empty:
            print(f"[{symbol}] ❌ Pas de données OHLCV pour backtest")
            await pool.close()
            return

        print(f"[{symbol}] ✅ Données OHLCV chargées ({len(df)} lignes), début: {df.index.min()}, fin: {df.index.max()}")

        # Filtrer les données selon intervalle demandé (ex: "1h", "3d", "5m")
        try:
            offset = to_offset(interval)
            cutoff_time = df.index.max() - offset
            df = df[df.index >= cutoff_time]
            print(f"[{symbol}] ⏱ Filtrage backtest sur intervalle {interval} : {len(df)} lignes restantes")
        except Exception as e:
            print(f"[{symbol}] ⚠️ Erreur parsing de l’intervalle '{interval}': {e}")

        # Analyse avec la stratégie choisie
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
    dsn = os.environ.get("PG_DSN")
    asyncio.run(run_backtest_async(symbol, interval, dsn))
