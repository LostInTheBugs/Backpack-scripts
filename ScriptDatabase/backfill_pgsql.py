import asyncio
from datetime import datetime, timezone, timedelta
import time
import asyncpg
from utils.public import get_ohlcv, format_table_name
import aiohttp
import os
import logging
from typing import List, Optional

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
CHUNK_SIZE_SECONDS = 24 * 3600  # 1 jour
LIMIT_PER_REQUEST = 1000
RETENTION_DAYS = 90
MAX_RETRIES = 3
RETRY_DELAY = 1  # secondes

async def fetch_all_symbols() -> List[str]:
    """Récupère tous les symboles PERP depuis l'API Backpack"""
    url = "https://api.backpack.exchange/api/v1/tickers"
    
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

async def create_table_if_not_exists(conn: asyncpg.Connection, symbol: str) -> None:
    """Crée la table et l'hypertable si elles n'existent pas"""
    table_name = format_table_name(symbol)
    
    # Créer la table
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            symbol TEXT NOT NULL,
            interval_sec INTEGER NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            open NUMERIC NOT NULL,
            high NUMERIC NOT NULL,
            low NUMERIC NOT NULL,
            close NUMERIC NOT NULL,
            volume NUMERIC NOT NULL DEFAULT 0,
            PRIMARY KEY (symbol, interval_sec, timestamp)
        );
    """)
    
    # Créer l'hypertable
    try:
        await conn.execute(f"""
            SELECT create_hypertable('{table_name}', 'timestamp', 
                                   if_not_exists => TRUE,
                                   chunk_time_interval => INTERVAL '1 day');
        """)
        logger.debug(f"Hypertable créée/vérifiée pour {table_name}")
    except Exception as e:
        logger.warning(f"Erreur création hypertable pour {table_name}: {e}")

    # Créer un index sur le symbol pour optimiser les requêtes
    try:
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol_timestamp 
            ON {table_name} (symbol, timestamp DESC);
        """)
    except Exception as e:
        logger.warning(f"Erreur création index pour {table_name}: {e}")

async def get_last_timestamp(conn: asyncpg.Connection, symbol: str) -> Optional[int]:
    """Récupère le dernier timestamp disponible pour un symbole"""
    table_name = format_table_name(symbol)
    try:
        result = await conn.fetchval(f"""
            SELECT EXTRACT(EPOCH FROM MAX(timestamp))::INTEGER 
            FROM {table_name} 
            WHERE symbol = $1
        """, symbol)
        return result
    except Exception as e:
        logger.debug(f"Erreur récupération dernier timestamp pour {symbol}: {e}")
        return None

async def clean_old_data(conn: asyncpg.Connection, symbol: str, retention_days: int) -> None:
    """Nettoie les données anciennes"""
    table_name = format_table_name(symbol)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    try:
        result = await conn.execute(f"""
            DELETE FROM {table_name} 
            WHERE timestamp < $1
        """, cutoff_dt)
        logger.info(f"Nettoyage données anciennes dans {table_name} : {result}")
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage de {table_name}: {e}")

async def insert_ohlcv_batch(conn: asyncpg.Connection, symbol: str, interval_sec: int, ohlcv_list: List) -> int:
    """Insère un batch de données OHLCV"""
    if not ohlcv_list:
        return 0
        
    table_name = format_table_name(symbol)
    values = []
    
    for item in ohlcv_list:
        try:
            ts = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc)
            open_, high, low, close_, volume = map(float, item[1:6])
            
            # Validation des données
            if any(val < 0 for val in [open_, high, low, close_]):
                logger.warning(f"Prix négatif détecté pour {symbol} à {ts}, ignoré")
                continue
                
            values.append((symbol, interval_sec, ts, open_, high, low, close_, volume))
        except (ValueError, IndexError) as e:
            logger.warning(f"Erreur parsing données pour {symbol}: {e}")
            continue

    if not values:
        return 0

    # Utiliser executemany pour de meilleures performances
    stmt = f"""
        INSERT INTO {table_name} (symbol, interval_sec, timestamp, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (symbol, interval_sec, timestamp) DO NOTHING
    """
    
    try:
        async with conn.transaction():
            await conn.executemany(stmt, values)
        
        inserted_count = len(values)
        logger.info(f"Inséré {inserted_count} bougies dans {table_name}")
        return inserted_count
        
    except Exception as e:
        logger.error(f"Erreur insertion batch pour {symbol}: {e}")
        return 0

async def backfill_symbol(pool: asyncpg.Pool, symbol: str, days: int = RETENTION_DAYS) -> None:
    """Effectue le backfill pour un symbole donné"""
    logger.info(f"Début backfill pour {symbol}")
    
    now = int(time.time())
    interval_sec = 60  # 1 minute
    total_inserted = 0

    async with pool.acquire() as conn:
        await create_table_if_not_exists(conn, symbol)
        
        # Récupérer le dernier timestamp disponible
        last_ts = await get_last_timestamp(conn, symbol)
        if last_ts:
            # Commencer après le dernier timestamp disponible
            start = last_ts + interval_sec
            logger.info(f"Reprise du backfill pour {symbol} depuis {datetime.utcfromtimestamp(start)}")
        else:
            # Backfill complet
            start = now - days * 24 * 3600
            logger.info(f"Backfill complet pour {symbol} depuis {datetime.utcfromtimestamp(start)}")
        
        # Nettoyer les anciennes données seulement si c'est un backfill complet
        if not last_ts:
            await clean_old_data(conn, symbol, days)

    current_start = start
    consecutive_failures = 0
    
    while current_start < now and consecutive_failures < 3:
        current_end = min(current_start + CHUNK_SIZE_SECONDS, now)
        logger.info(f"Backfill {symbol} de {datetime.utcfromtimestamp(current_start)} à {datetime.utcfromtimestamp(current_end)}")

        batch_start = current_start
        batch_success = False
        
        while batch_start < current_end:
            if batch_start >= now:
                logger.info(f"startTime {datetime.utcfromtimestamp(batch_start)} dans le futur, arrêt")
                break

            logger.debug(f"Appel get_ohlcv() pour {symbol} startTime = {batch_start}")
            
            try:
                data = get_ohlcv(symbol, interval=INTERVAL, limit=LIMIT_PER_REQUEST, startTime=batch_start)
                
                if not data:
                    logger.warning(f"Pas de données pour {symbol} à partir de {datetime.utcfromtimestamp(batch_start)}")
                    break

                async with pool.acquire() as conn:
                    inserted = await insert_ohlcv_batch(conn, symbol, interval_sec, data)
                    total_inserted += inserted

                batch_success = True
                consecutive_failures = 0

                last_ts_ms = data[-1][0]
                last_ts_sec = last_ts_ms // 1000

                if len(data) < LIMIT_PER_REQUEST:
                    # Moins de données que la limite = fin du batch
                    break

                batch_start = last_ts_sec + interval_sec
                
                # Petite pause pour éviter de surcharger l'API
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Erreur lors du traitement de {symbol}: {e}")
                consecutive_failures += 1
                await asyncio.sleep(RETRY_DELAY * consecutive_failures)
                break

        if not batch_success:
            consecutive_failures += 1
            logger.warning(f"Échec batch pour {symbol}, tentatives échouées: {consecutive_failures}")
        
        current_start = current_end

    logger.info(f"Backfill terminé pour {symbol}, total inséré: {total_inserted}")

async def main():
    """Fonction principale"""
    logger.info("Début du processus de backfill")
    
    try:
        # Créer le pool de connexions
        pool = await asyncpg.create_pool(
            dsn=PG_DSN,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        
        # Récupérer les symboles
        symbols = await fetch_all_symbols()
        if not symbols:
            logger.error("Aucun symbole récupéré, arrêt.")
            return

        logger.info(f"Traitement de {len(symbols)} symboles")
        
        # Traiter les symboles en parallèle (avec limite)
        semaphore = asyncio.Semaphore(3)  # Max 3 symboles en parallèle
        
        async def process_symbol_with_semaphore(symbol):
            async with semaphore:
                await backfill_symbol(pool, symbol, RETENTION_DAYS)
        
        tasks = [process_symbol_with_semaphore(symbol) for symbol in symbols]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        await pool.close()
        logger.info("Processus de backfill terminé")
        
    except Exception as e:
        logger.error(f"Erreur critique dans main(): {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())