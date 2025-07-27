import requests
import asyncpg
import asyncio
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

async def update_markets_table(pool):
    url = "https://api.backpack.exchange/api/v1/markets"
    response = requests.get(url)
    response.raise_for_status()
    markets = response.json()

    async with pool.acquire() as conn:
        async with conn.transaction():
            for m in markets:
                await conn.execute("""
                    INSERT INTO backpack_markets (name, baseSymbol, quoteSymbol, marketType, orderBookState, createdAt, raw_json)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (name) DO UPDATE SET
                        baseSymbol = EXCLUDED.baseSymbol,
                        quoteSymbol = EXCLUDED.quoteSymbol,
                        marketType = EXCLUDED.marketType,
                        orderBookState = EXCLUDED.orderBookState,
                        createdAt = EXCLUDED.createdAt,
                        raw_json = EXCLUDED.raw_json
                """, m["name"], m["baseSymbol"], m["quoteSymbol"], m["marketType"], m["orderBookState"], m["createdAt"], m)

async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    await update_markets_table(pool)
    await pool.close()
    print("Mise à jour terminée")

if __name__ == "__main__":
    asyncio.run(main())
