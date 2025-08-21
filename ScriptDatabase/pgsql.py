# ScriptDatabase/pgsql.py
import asyncpg
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

async def get_symbols():
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol FROM backpack_markets WHERE marketType = 'PERP';")
    await pool.close()
    return [row["symbol"] for row in rows]

async def get_symbol_info(symbol: str):
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM backpack_markets WHERE symbol = $1;", symbol)
    await pool.close()
    return row

def get_symbol_info_sync(symbol: str):
    import asyncio
    from ScriptDatabase.pgsql import get_symbol_info
    return asyncio.run(get_symbol_info(symbol))
