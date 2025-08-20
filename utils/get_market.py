# utils/get_market.py
import os
import asyncpg
import pandas as pd
from datetime import datetime, timedelta, timezone
from utils.position_utils import get_open_positions
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from utils.logger import log

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

_pool = None  # pool global


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=PG_DSN)
    return _pool


async def get_market(symbol: str):
    """Récupère les infos marché et le prix actuel pour un symbole"""
    try:
        pool = await get_pool()

        # Récupérer les infos marché depuis la BDD
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT symbol, baseSymbol, quoteSymbol, marketType, orderBookState, createdAt
                FROM backpack_markets
                WHERE symbol = $1
            """, symbol)

        result = {}
        if row:
            result = dict(row)
        else:
            log(f"[WARN] Marché {symbol} non trouvé en backpack_markets, utilisation du prix OHLCV", level="info")
            # Remplir les champs pour compatibilité
            result["symbol"] = symbol
            result["baseSymbol"] = symbol.split("_")[0]
            result["quoteSymbol"] = symbol.split("_")[1]
            result["marketType"] = "PERP"
            result["orderBookState"] = None
            result["createdAt"] = None

        # Valeurs par défaut
        result["pnl"] = 0.0
        result["price"] = None

        # Vérifier positions ouvertes
        open_positions = await get_open_positions()
        position = open_positions.get(symbol)

        # Récupérer le prix actuel depuis la BDD OHLCV (bougie 1s)
        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=10)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)

        if df is not None and not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
            df.set_index('timestamp', inplace=True)
            df = df.sort_index()
            df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)

            current_price = float(df.iloc[-1]["close"])
            result["price"] = current_price

            if position:
                entry_price = position["entry_price"]
                side = position["side"]

                if side == "long":
                    pnl = (current_price - entry_price) / entry_price * 100
                else:  # short
                    pnl = (entry_price - current_price) / entry_price * 100

                result["pnl"] = pnl
                result["side"] = side
                result["entry_price"] = entry_price

        return result

    except Exception as e:
        log(f"⚠️ Erreur get_market({symbol}): {e}", level="error")
        return None


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
