import asyncio
import os
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal
import pandas as pd
import asyncpg

async def fetch_ohlcv_from_db(pool, symbol, interval):
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

async def run_backtest_async(symbol: str, interval: str, pool):
    try:
        table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))

        interval_map = {
            '1s': 1,
            '1m': 60,
            '1h': 3600,
            '1d': 86400,
        }
        interval_sec = interval_map.get(interval, 1)

        async with pool.acquire() as conn:
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                WHERE interval_sec = $1
                ORDER BY timestamp
            """
            rows = await conn.fetch(query, interval_sec)

        if not rows:
            log(f"[{symbol}] ❌ Pas de données OHLCV pour le backtest avec intervalle {interval} ({interval_sec}s)")
            return

        data = [dict(row) for row in rows]
        df = pd.DataFrame(data)

        if 'timestamp' not in df.columns:
            log(f"[{symbol}] ❌ La colonne 'timestamp' est absente dans les données")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('UTC')
        df.set_index('timestamp', inplace=True)

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        log(f"[{symbol}] ✅ Données OHLCV chargées ({len(df)} lignes), début: {df.index.min()}, fin: {df.index.max()}")

        signal = get_combined_signal(df)
        log(f"[{symbol}] Backtest signal final: {signal}")

    except Exception as e:
        log(f"[{symbol}] 💥 Exception durant le backtest: {e}")
        traceback.print_exc()

async def main():
    dsn = os.environ.get("PG_DSN")
    if not dsn:
        log("❌ Variable d'environnement PG_DSN non définie")
        return

    pool = await asyncpg.create_pool(dsn=dsn)
    try:
        # Exemple : lancer plusieurs backtests dans la même session
        symbols_intervals = [
            ("ETH_USDC_PERP", "1h"),
            ("BTC_USDC_PERP", "1h"),
            # ajoute d'autres symboles et intervalles ici
        ]

        for symbol, interval in symbols_intervals:
            log(f"[{symbol}] 🧪 Lancement du backtest en {interval}")
            await run_backtest_async(symbol, interval, pool)
    finally:
        await pool.close()
        log("Pool de connexion fermé, fin du programme.")

if __name__ == "__main__":
    asyncio.run(main())
