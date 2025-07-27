import os
import asyncpg
import asyncio

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

async def get_market(symbol: str):
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT name, baseSymbol, quoteSymbol, marketType, orderBookState, createdAt
            FROM backpack_markets
            WHERE name = $1
        """, symbol)
    await pool.close()

    if not row:
        print(f"⚠️ Marché {symbol} non trouvé en base locale")
        return None

    # Transformer le record en dict
    return dict(row)

# Pour usage synchrone simple (juste pour tests)
def get_market_sync(symbol: str):
    return asyncio.run(get_market(symbol))
