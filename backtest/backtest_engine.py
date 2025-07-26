import asyncio
import asyncpg
import pandas as pd
import os
from datetime import datetime, timezone
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal

async def fetch_ohlcv_from_db(pool, symbol, interval):
    """
    Récupère les données OHLCV depuis la base PostgreSQL pour un symbole et interval donné.
    interval: '1s', '1m', '1h', '1d', etc.
    """
    table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))
    
    # Exemple simplifié: récupérer tout le contenu
    # Tu peux optimiser selon intervalle demandé
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
            
            # Convertir en DataFrame pandas
            data = [dict(row) for row in rows]
            df = pd.DataFrame(data)
            # Convert timestamp en datetime au besoin (assure tz aware)
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('UTC')
            return df
        except Exception as e:
            log(f"[{symbol}] ❌ Erreur fetch OHLCV backtest: {e}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, interval: str, dsn: str):
    pool = await asyncpg.create_pool(dsn=dsn)
    async with pool.acquire() as conn:
        table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))
        
        interval_sec_map = {
            "1s": 1,
            "1m": 60,
            "1h": 3600,
            "1d": 86400,
            "1w": 604800,
        }
        
        if interval not in interval_sec_map:
            print(f"[{symbol}] ❌ Intervalle inconnu : {interval}")
            await pool.close()
            return
        
        interval_sec = interval_sec_map[interval]
        
        query = f"""
            SELECT timestamp, open, high, low, close, volume
            FROM {table_name}
            WHERE interval_sec = $1
            ORDER BY timestamp
        """
        
        rows = await conn.fetch(query, interval_sec)
        
        if not rows:
            print(f"[{symbol}] ❌ Pas de données OHLCV pour le backtest")
            await pool.close()
            return
        
        df = pd.DataFrame(rows)
        if df.empty:
            print(f"[{symbol}] ❌ DataFrame vide après conversion")
            await pool.close()
            return
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        print(f"DEBUG avant appel get_combined_signal - index type: {type(df.index)}")
        
        from signals.macd_rsi_breakout import get_combined_signal
        signal = get_combined_signal(df)
        
        print(f"[{symbol}] Backtest signal final: {signal}")
    
    await pool.close()

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
