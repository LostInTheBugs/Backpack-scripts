import asyncio
import asyncpg
import pandas as pd
import os
import traceback
from utils.logger import log
from utils.position_tracker import PositionTracker
from datetime import timedelta

from live.live_engine import get_combined_signal  # dynamique selon la stratégie

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

async def run_backtest_async(symbol: str, interval: str, dsn: str):
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        df = await fetch_ohlcv_from_db(pool, symbol)
        await pool.close()

        if df.empty:
            log(f"[{symbol}] ❌ Pas de données OHLCV")
            return

        log(f"[{symbol}] ✅ Début du backtest avec {len(df)} bougies")

        tracker = PositionTracker(symbol)
        stats = {"total": 0, "win": 0, "loss": 0, "pnl": []}

        for current_time in df.index:
            current_df = df.loc[:current_time]
            if len(current_df) < 100:
                continue

            signal = get_combined_signal(current_df)

            current_price = current_df.iloc[-1]["close"]

            # Ouvre position si signal et aucune position
            if signal in ("BUY", "SELL") and not tracker.is_open():
                tracker.open(signal, current_price, current_time)

            # Met à jour trailing stop si position ouverte
            if tracker.is_open():
                tracker.update_trailing_stop(current_price, current_time)

                # Ferme si stop touché
                if tracker.should_close(current_price):
                    pnl = tracker.close(current_price, current_time)
                    stats["total"] += 1
                    stats["pnl"].append(pnl)
                    if pnl >= 0:
                        stats["win"] += 1
                    else:
                        stats["loss"] += 1

        log(f"[{symbol}] 🔚 Backtest terminé")
        if stats["total"] > 0:
            pnl_total = sum(stats["pnl"])
            pnl_moyen = pnl_total / stats["total"]
            pnl_median = pd.Series(stats["pnl"]).median()
            win_rate = stats["win"] / stats["total"] * 100
            log(f"[{symbol}] 📊 Positions: {stats['total']} | Gagnantes: {stats['win']} | Perdantes: {stats['loss']}")
            log(f"[{symbol}] 📈 PnL total: {pnl_total:.2f}% | moyen: {pnl_moyen:.2f}% | médian: {pnl_median:.2f}% | taux de succès: {win_rate:.2f}%")
        else:
            log(f"[{symbol}] ⚠️ Aucune position prise")

    except Exception as e:
        log(f"[{symbol}] 💥 Exception dans le backtest complet: {e}")
        traceback.print_exc()

def run_backtest(symbol, interval):
    dsn = os.environ.get("PG_DSN")
    asyncio.run(run_backtest_async(symbol, interval, dsn))
