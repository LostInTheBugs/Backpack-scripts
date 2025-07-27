import os
import asyncpg
from datetime import datetime, timedelta, timezone
from utils.ohlcv_utils import get_ohlcv_df
from utils.position_utils import get_open_positions

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
    pool = await get_pool()

    # Récupérer les infos de marché
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT symbol, baseSymbol, quoteSymbol, marketType, orderBookState, createdAt
            FROM backpack_markets
            WHERE symbol = $1
        """, symbol)

    if not row:
        print(f"⚠️ Marché {symbol} non trouvé en base locale")
        return None

    result = dict(row)

    # Récupérer positions ouvertes
    open_positions = await get_open_positions()
    position = open_positions.get(symbol)

    if position:
        # Récupérer le prix actuel depuis OHLCV (dernière bougie)
        df = get_ohlcv_df(symbol, "1s")
        if df.empty:
            result["pnl"] = 0.0
            return result

        current_price = float(df.iloc[-1]["close"])
        entry_price = position["entry_price"]
        side = position["side"]

        if side == "long":
            pnl = (current_price - entry_price) / entry_price * 100
        else:  # short
            pnl = (entry_price - current_price) / entry_price * 100

        result["pnl"] = pnl
    else:
        result["pnl"] = 0.0

    return result

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
