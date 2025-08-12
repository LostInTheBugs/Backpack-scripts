import asyncio
from datetime import datetime, timezone, timedelta
import time
import asyncpg
import os
import logging
from typing import List, Optional

from bpx.public import Public  # import SDK bpx-py

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backfill.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

INTERVAL = "1m"
CHUNK_SIZE_SECONDS = 6 * 3600  # 6 heures
LIMIT_PER_REQUEST = 1000
RETENTION_DAYS = 90
MAX_RETRIES = 3
RETRY_DELAY = 1
API_RATE_LIMIT_DELAY = 0.2  # 200ms entre les requêtes

public = Public()  # Instance du client public du SDK bpx-py

def timestamp_to_datetime_str(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

async def get_last_timestamp(conn, symbol: str) -> int | None:
    """
    Retourne le timestamp UNIX (en secondes) de la dernière bougie présente en base pour ce symbole,
    ou None si aucune donnée.
    """
    table_name = f"ohlcv__{symbol.lower().replace('_', '__')}"
    query = f"SELECT timestamp FROM {table_name} ORDER BY timestamp DESC LIMIT 1"
    row = await conn.fetchrow(query)
    if row is None:
        return None
    # row['timestamp'] est un datetime timezone-aware, on le convertit en timestamp unix (secondes)
    return int(row['timestamp'].timestamp())

async def create_table_if_not_exists(conn, symbol: str):
    table_name = f"ohlcv__{symbol.lower().replace('_', '__')}"
    query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        timestamp TIMESTAMP WITH TIME ZONE PRIMARY KEY,
        open FLOAT NOT NULL,
        high FLOAT NOT NULL,
        low FLOAT NOT NULL,
        close FLOAT NOT NULL,
        volume FLOAT NOT NULL
    );
    """
    await conn.execute(query)

async def insert_ohlcv_batch(conn, symbol: str, interval_sec: int, data: list) -> int:
    """
    Insère une liste de candles OHLCV dans la table.
    data est une liste de listes, chaque élément = [timestamp_ms, open, high, low, close, volume]
    """
    table_name = f"ohlcv__{symbol.lower().replace('_', '__')}"
    query = f"""
    INSERT INTO {table_name} (timestamp, open, high, low, close, volume)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (timestamp) DO NOTHING
    """
    count = 0
    for candle in data:
        timestamp_ms = candle[0]
        ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        try:
            await conn.execute(query, ts, float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4]), float(candle[5]))
            count += 1
        except Exception as e:
            logger.error(f"Erreur insertion candle {ts} pour {symbol}: {e}")
    return count

async def clean_old_data(conn, symbol: str, retention_days: int):
    table_name = f"ohlcv__{symbol.lower().replace('_', '__')}"
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    query = f"DELETE FROM {table_name} WHERE timestamp < $1"
    deleted = await conn.execute(query, cutoff_date)
    logger.info(f"Nettoyage: {deleted} lignes supprimées dans {table_name} avant {cutoff_date}")
    
# Nouvelle fonction sync qui utilise le SDK bpx-py
def get_ohlcv_bpx_sdk(symbol: str, interval: str = "1m", limit: int = 21, startTime: int = None, endTime: int = 0):
    """
    Wrapper sync autour de public.get_klines.
    startTime et endTime en secondes UNIX (int).
    """
    if startTime is None:
        raise ValueError("startTime doit être fourni")
    # Adapter interval pour SDK, il accepte '1m', '5m', etc. donc ok
    try:
        data = public.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=startTime * 1000,
            end_time=endTime * 1000 if endTime else 0,
        )
        return data
    except Exception as e:
        logger.error(f"Erreur get_ohlcv_bpx_sdk({symbol}): {e}")
        return None

# Fonction async pour appeler la fonction sync sans bloquer
async def get_ohlcv_async(symbol: str, interval: str = "1m", limit: int = 21, startTime: int = None, endTime: int = 0):
    return await asyncio.to_thread(get_ohlcv_bpx_sdk, symbol, interval, limit, startTime, endTime)

async def fetch_all_symbols() -> List[str]:
    url = "https://api.backpack.exchange/api/v1/tickers"
    import aiohttp
    for attempt in range(MAX_RETRIES):
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.error(f"Erreur API Backpack : HTTP {resp.status}")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                            continue
                        return []
                    data = await resp.json()
        except asyncio.TimeoutError:
            logger.error(f"Timeout lors de la récupération des symboles (tentative {attempt + 1})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            return []
        except Exception as e:
            logger.error(f"Exception lors de la récupération des symboles : {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            return []

    symbols = [t["symbol"] for t in data if "_PERP" in t.get("symbol", "")]
    logger.info(f"Récupéré {len(symbols)} symboles PERP")
    return symbols

# Reste des fonctions create_table_if_not_exists, get_last_timestamp, clean_old_data, insert_ohlcv_batch inchangées...

async def get_symbol_listing_date(symbol: str) -> Optional[int]:
    now = int(time.time())
    test_dates = [
        now - 30 * 24 * 3600,
        now - 90 * 24 * 3600,
        now - 180 * 24 * 3600,
        now - 365 * 24 * 3600,
    ]

    logger.info(f"Now timestamp: {now} ({timestamp_to_datetime_str(now)})")
    for test_date in test_dates:
        logger.info(f"Testing listing date candidate: {test_date} ({timestamp_to_datetime_str(test_date)})")
        try:
            data = await get_ohlcv_async(symbol, interval=INTERVAL, limit=1, startTime=test_date)
            if data:
                first_candle_ts = data[0][0] // 1000
                logger.info(f"Première bougie trouvée pour {symbol}: {timestamp_to_datetime_str(first_candle_ts)}")
                return first_candle_ts
            await asyncio.sleep(API_RATE_LIMIT_DELAY)
        except Exception as e:
            logger.debug(f"Erreur test date {timestamp_to_datetime_str(test_date)} pour {symbol}: {e}")
            continue
    logger.warning(f"Impossible de déterminer la date de listing pour {symbol}")
    return None

async def backfill_symbol(pool: asyncpg.Pool, symbol: str, days: int = RETENTION_DAYS) -> None:
    logger.info(f"🚀 Début backfill pour {symbol}")

    now = int(time.time())
    interval_sec = 60
    total_inserted = 0

    async with pool.acquire() as conn:
        await create_table_if_not_exists(conn, symbol)
        last_ts = await get_last_timestamp(conn, symbol)

        if last_ts and last_ts < now:
            start = last_ts + interval_sec
            logger.info(f"📈 Reprise backfill pour {symbol} depuis {timestamp_to_datetime_str(start)}")
        else:
            logger.info(f"🔍 Recherche date de listing pour {symbol}")
            listing_date = await get_symbol_listing_date(symbol)
            if not listing_date:
                logger.error(f"❌ Impossible de déterminer la date de listing pour {symbol}")
                return
            retention_start = now - days * 24 * 3600
            start = max(listing_date, retention_start)
            logger.info(f"📅 Backfill complet pour {symbol} depuis {timestamp_to_datetime_str(start)}")
            await clean_old_data(conn, symbol, days)

    if start >= now:
        logger.warning(f"⚠️ Start timestamp {timestamp_to_datetime_str(start)} est dans le futur pour {symbol}")
        return

    current_start = start
    consecutive_failures = 0

    while current_start < now and consecutive_failures < 5:
        current_end = min(current_start + CHUNK_SIZE_SECONDS, now - 60)
        if current_end <= current_start:
            logger.info(f"⏹️ Chunk trop petit pour {symbol}, arrêt")
            break
        logger.info(f"⏳ Traitement {symbol}: {timestamp_to_datetime_str(current_start)} → {timestamp_to_datetime_str(current_end)}")

        batch_start = current_start
        batch_success = False

        while batch_start < current_end:
            if batch_start >= now - 60:
                logger.info(f"⏭️ Approche du temps présent pour {symbol}, arrêt du batch")
                break
            try:
                data = await get_ohlcv_async(symbol, interval=INTERVAL, limit=LIMIT_PER_REQUEST, startTime=batch_start)
                if not data:
                    logger.warning(f"📭 Pas de données pour {symbol} à partir de {timestamp_to_datetime_str(batch_start)}")
                    break

                latest_data_ts = data[-1][0] // 1000
                if latest_data_ts > now:
                    logger.warning(f"⚠️ Données futures reçues pour {symbol}, filtrage nécessaire")
                    data = [d for d in data if d[0] // 1000 <= now]

                if data:
                    async with pool.acquire() as conn:
                        inserted = await insert_ohlcv_batch(conn, symbol, interval_sec, data)
                        total_inserted += inserted

                batch_success = True
                consecutive_failures = 0

                last_ts_ms = data[-1][0]
                last_ts_sec = last_ts_ms // 1000
                batch_start = last_ts_sec + interval_sec

                if len(data) < LIMIT_PER_REQUEST:
                    logger.info(f"📊 Fin des données disponibles pour {symbol}")
                    break

                await asyncio.sleep(API_RATE_LIMIT_DELAY)

            except Exception as e:
                logger.error(f"❌ Erreur lors du traitement de {symbol}: {e}")
                consecutive_failures += 1
                await asyncio.sleep(RETRY_DELAY * consecutive_failures)
                break

        if not batch_success:
            consecutive_failures += 1
            logger.warning(f"⚠️ Échec batch pour {symbol}, tentatives échouées: {consecutive_failures}")

        current_start = current_end

    logger.info(f"✅ Backfill terminé pour {symbol}, total inséré: {total_inserted}")

async def main():
    logger.info("🎯 Début du processus de backfill")

    try:
        pool = await asyncpg.create_pool(
            dsn=PG_DSN,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        symbols = await fetch_all_symbols()
        if not symbols:
            logger.error("❌ Aucun symbole récupéré, arrêt.")
            return

        logger.info(f"📋 Traitement de {len(symbols)} symboles")

        for i, symbol in enumerate(symbols, 1):
            logger.info(f"🔄 Progression: {i}/{len(symbols)} - Traitement de {symbol}")
            try:
                await backfill_symbol(pool, symbol, RETENTION_DAYS)
                if i < len(symbols):
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"❌ Erreur lors du traitement de {symbol}: {e}")
                continue

        await pool.close()
        logger.info("🎉 Processus de backfill terminé")

    except Exception as e:
        logger.error(f"💥 Erreur critique dans main(): {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
