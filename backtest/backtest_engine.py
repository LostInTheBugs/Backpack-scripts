import asyncio
import asyncpg
import pandas as pd
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

async def run_backtest_async(symbol, interval, dsn):

    print(f"DEBUG avant conversion index: {df.index}, type: {type(df.index)}")
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    print(f"DEBUG après conversion index: {df.index}, type: {type(df.index)}")

    log(f"[{symbol}] 🧪 Début backtest async interval={interval}")

    pool = await asyncpg.create_pool(dsn=dsn)

    df = await fetch_ohlcv_from_db(pool, symbol, interval)
    if df.empty:
        log(f"[{symbol}] ⚠️ DataFrame vide, backtest annulé")
        await pool.close()
        return

    # Convertir colonnes Decimal en float pour éviter les erreurs de type
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = df[col].astype(float)

    try:
        signal = get_combined_signal(df)
        log(f"[{symbol}] Backtest signal final: {signal}")
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur backtest: {e}")
        import traceback
        traceback.print_exc()

    await pool.close()
    log(f"[{symbol}] ✅ Fin backtest")

def run_backtest(symbol, interval):
    """
    Fonction synchrone qui peut être appelée hors boucle asyncio.
    """
    dsn = os.environ.get("PG_DSN")
    import asyncio
    asyncio.run(run_backtest_async(symbol, interval, dsn))
