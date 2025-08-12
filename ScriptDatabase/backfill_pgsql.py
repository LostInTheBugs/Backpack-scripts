import os
import asyncpg
import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("PG_DSN non défini")

RETENTION_DAYS = 90
INTERVAL_SEC = "1m"
BATCH_SECONDS = 3600
MAX_CONCURRENT_TASKS = 5  # Limite de parallélisme

def table_name_from_symbol(symbol: str) -> str:
    return "ohlcv_" + symbol.lower().replace("_", "__")

async def fetch_all_symbols() -> list[str]:
    url = "https://api.backpack.exchange/api/v1/tickers"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"❌ Erreur API Backpack : HTTP {resp.status}")
                    return []
                data = await resp.json()
    except Exception as e:
        print(f"❌ Exception lors de la récupération des symboles : {e}")
        return []

    symbols = [t["symbol"] for t in data if "_PERP" in t.get("symbol", "")]
    return symbols

async def create_or_clean_table(conn, symbol):
    table_name = table_name_from_symbol(symbol)
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            symbol TEXT NOT NULL,
            interval_sec INTEGER NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume NUMERIC,
            PRIMARY KEY (symbol, interval_sec, timestamp)
        );
    """)
    await conn.execute(f"DELETE FROM {table_name};")
    print(f"🧹 Table {table_name} nettoyée.")

async def fetch_and_insert(symbol, pool, semaphore):
    async with semaphore:
        table_name = table_name_from_symbol(symbol)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=RETENTION_DAYS)

        async with aiohttp.ClientSession() as session:
            current = start_time
            total_inserted = 0
            while current < end_time:
                next_batch = min(current + timedelta(seconds=BATCH_SECONDS), end_time)
                url = (
                    f"https://api.backpack.exchange/api/v1/klines"
                    f"?symbol={symbol}&interval=1s"
                    f"&startTime={int(current.timestamp()*1000)}"
                    f"&endTime={int(next_batch.timestamp()*1000)}"
                )

                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            print(f"❌ Erreur API {symbol} : {resp.status}")
                            await asyncio.sleep(1)
                            continue
                        data = await resp.json()
                except Exception as e:
                    print(f"❌ Exception API {symbol}: {e}")
                    await asyncio.sleep(1)
                    continue

                rows = []
                for candle in data:
                    ts = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc)
                    rows.append((
                        symbol, INTERVAL_SEC, ts,
                        float(candle[1]),
                        float(candle[2]),
                        float(candle[3]),
                        float(candle[4]),
                        float(candle[5])
                    ))

                if rows:
                    async with pool.acquire() as conn:
                        await conn.executemany(f"""
                            INSERT INTO {table_name} (symbol, interval_sec, timestamp, open, high, low, close, volume)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                            ON CONFLICT (symbol, interval_sec, timestamp) DO NOTHING
                        """, rows)
                    total_inserted += len(rows)

                print(f"✅ {symbol} : {len(rows)} bougies insérées ({current} → {next_batch})")
                current = next_batch
                await asyncio.sleep(0.2)

            print(f"🎉 {symbol} terminé : {total_inserted} bougies insérées.")

async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    symbols = await fetch_all_symbols()
    if not symbols:
        print("❌ Pas de symboles récupérés, arrêt.")
        await pool.close()
        return

    # Nettoyer les tables avant insertion
    async with pool.acquire() as conn:
        for sym in symbols:
            await create_or_clean_table(conn, sym)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    tasks = [fetch_and_insert(sym, pool, semaphore) for sym in symbols]

    await asyncio.gather(*tasks)
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
