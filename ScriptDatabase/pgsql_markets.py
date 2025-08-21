# ScriptDatabase/pgsql_markets.py
import requests
import asyncpg
import asyncio
import os
import json
from datetime import datetime
from utils.logger import log

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
                created_at_dt = datetime.fromisoformat(m["createdAt"])
                raw_json_str = json.dumps(m)  # <-- convertir dict en JSON string

                step_size = float(m.get("quantityIncrement", 0))
                tick_size = float(m.get("priceIncrement", 0))
                min_qty = float(m.get("minQuantity", 0))

                await conn.execute("""
                    INSERT INTO backpack_markets (
                        symbol, baseSymbol, quoteSymbol, marketType, orderBookState, createdAt,
                        raw_json, stepSize, tickSize, minQty
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (symbol) DO UPDATE SET
                        baseSymbol = EXCLUDED.baseSymbol,
                        quoteSymbol = EXCLUDED.quoteSymbol,
                        marketType = EXCLUDED.marketType,
                        orderBookState = EXCLUDED.orderBookState,
                        createdAt = EXCLUDED.createdAt,
                        raw_json = EXCLUDED.raw_json,
                        stepSize = EXCLUDED.stepSize,
                        tickSize = EXCLUDED.tickSize,
                        minQty = EXCLUDED.minQty
                """, m["symbol"], m["baseSymbol"], m["quoteSymbol"], m["marketType"], m["orderBookState"],
                     created_at_dt, raw_json_str, step_size, tick_size, min_qty)
                
async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    await update_markets_table(pool)
    await pool.close()
    log(f"Mise à jour terminée", level="DEBUG")

if __name__ == "__main__":
    asyncio.run(main())
