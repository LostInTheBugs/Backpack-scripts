import asyncio
from datetime import datetime, timezone, timedelta
import time
import asyncpg
from utils.public import get_ohlcv, format_table_name
import aiohttp
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

INTERVAL = "1m"
CHUNK_SIZE_SECONDS = 24 * 3600  # 1 jour
LIMIT_PER_REQUEST = 1000
RETENTION_DAYS = 90

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

async def create_table_if_not_exists(conn, symbol):
    table_name = format_table_name(symbol)
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
    try:
        await conn.execute(f"SELECT create_hypertable('{table_name}', 'timestamp', if_not_exists => TRUE);")
    except Exception as e:
        print(f"⚠️ Erreur création hypertable pour {table_name}: {e}")

async def clean_old_data(conn, symbol, retention_days):
    table_name = format_table_name(symbol)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await conn.execute(f"DELETE FROM {table_name} WHERE timestamp < $1", cutoff_dt)
    print(f"🧹 Nettoyage données anciennes dans {table_name} : {result}")

async def insert_ohlcv_batch(conn, symbol, interval_sec, ohlcv_list):
    if not ohlcv_list:
        return
    table_name = format_table_name(symbol)
    values = []
    for item in ohlcv_list:
        ts = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc)
        open_, high, low, close_, volume = map(float, item[1:6])
        values.append((symbol, ts, interval_sec, open_, high, low, close_, volume))

    stmt = f"""
    INSERT INTO {table_name} (symbol, timestamp, interval_sec, open, high, low, close, volume)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    ON CONFLICT (symbol, interval_sec, timestamp) DO NOTHING
    """
    async with conn.transaction():
        for val in values:
            await conn.execute(stmt, *val)
    print(f"📥 Inséré {len(values)} bougies dans {table_name}")

async def backfill_symbol(pool, symbol, days=RETENTION_DAYS):
    now = int(time.time())
    start = now - days * 24 * 3600
    interval_sec = 60  # 1 minute

    async with pool.acquire() as conn:
        await create_table_if_not_exists(conn, symbol)
        await clean_old_data(conn, symbol, days)

    current_start = start
    while current_start < now:
        current_end = min(current_start + CHUNK_SIZE_SECONDS, now)
        print(f"🔄 Backfill {symbol} de {datetime.utcfromtimestamp(current_start)} à {datetime.utcfromtimestamp(current_end)}")

        batch_start = current_start
        while batch_start < current_end:
            # S'assurer de ne pas demander un startTime dans le futur
            if batch_start >= now:
                print(f"⏭️ startTime {datetime.utcfromtimestamp(batch_start)} dans le futur, arrêt de la boucle.")
                break

            print(f"Appel get_ohlcv() startTime = {batch_start} ({datetime.utcfromtimestamp(batch_start)})")
            data = get_ohlcv(symbol, interval=INTERVAL, limit=LIMIT_PER_REQUEST, startTime=batch_start)
            
            if not data:
                print(f"❌ Pas de données pour {symbol} à partir de {datetime.utcfromtimestamp(batch_start)}. Arrêt du backfill sur cette période.")
                break  # On sort de la boucle batch pour passer à la tranche suivante ou arrêter

            async with pool.acquire() as conn:
                await insert_ohlcv_batch(conn, symbol, interval_sec, data)

            last_ts_ms = data[-1][0]
            last_ts_sec = last_ts_ms // 1000

            if len(data) < LIMIT_PER_REQUEST:
                # Moins de données que la limite = fin du batch
                break

            batch_start = last_ts_sec + interval_sec

        current_start = current_end


async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    symbols = await fetch_all_symbols()
    if not symbols:
        print("❌ Aucun symbole récupéré, arrêt.")
        return

    for symbol in symbols:
        await backfill_symbol(pool, symbol, RETENTION_DAYS)

    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
