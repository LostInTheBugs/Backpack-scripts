import asyncio
import asyncpg
from ScriptDatabase.backfill_pgsql import count_days_with_data
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

async def test_count_days(symbol: str):
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    async with pool.acquire() as conn:
        count = await count_days_with_data(conn, symbol)
        print(f"Nombre de jours avec données pour {symbol}: {count}")
    await pool.close()

if __name__ == "__main__":
    symbol = "BTC_USDC_PERP"  # ou un autre symbole que tu as en base
    asyncio.run(test_count_days(symbol))
