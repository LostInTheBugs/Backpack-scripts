import os
import asyncpg

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
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT symbol, baseSymbol, quoteSymbol, marketType, orderBookState, createdAt
            FROM backpack_markets
            WHERE symbol = $1
        """, symbol)

    if not row:
        print(f"⚠️ Marché {symbol} non trouvé en base locale")
        return None
    return dict(row)

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
