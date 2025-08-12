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
CHUNK_SIZE_SECONDS = 6 * 3600  # 6 heures (réduit pour éviter les timeouts)
LIMIT_PER_REQUEST = 1000
RETENTION_DAYS = 90
MAX_RETRIES = 3
RETRY_DELAY = 1
API_RATE_LIMIT_DELAY = 0.2  # 200ms entre les requêtes

def timestamp_to_datetime_str(ts: int) -> str:
    """Convertit un timestamp en string datetime lisible"""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

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
    
    try:
        await conn.execute(f"""
            SELECT create_hypertable('{table_name}', 'timestamp', 
                                   if_not_exists => TRUE,
                                   chunk_time_interval => INTERVAL '1 day');
        """)
        logger.debug(f"Hypertable créée/vérifiée pour {table_name}")
    except Exception as e:
        logger.warning(f"Erreur création hypertable pour {table_name}: {e}")

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
    except Exception:
        return None

async def get_symbol_listing_date(symbol: str) -> Optional[int]:
    """
    Récupère la date de listing d'un symbole en testant avec une requête minimale.
    Retourne le timestamp de début ou None si erreur.
    """
    # On va tester différentes dates pour trouver quand le symbole a été listé
    now = int(time.time())
    test_dates = [
        now - 30 * 24 * 3600,   # Il y a 30 jours
        now - 90 * 24 * 3600,   # Il y a 90 jours
        now - 180 * 24 * 3600,  # Il y a 180 jours
        now - 365 * 24 * 3600,  # Il y a 1 an
    ]
    
    for test_date in test_dates:
        try:
            logger.debug(f"Test date de listing pour {symbol}: {timestamp_to_datetime_str(test_date)}")
            data = get_ohlcv(symbol, interval=INTERVAL, limit=1, startTime=test_date)
            if data:
                first_candle_ts = data[0][0] // 1000  # Convertir ms en secondes
                logger.info(f"Première bougie trouvée pour {symbol}: {timestamp_to_datetime_str(first_candle_ts)}")
                return first_candle_ts
                
            # Attendre entre les tests pour éviter de surcharger l'API
            await asyncio.sleep(API_RATE_LIMIT_DELAY)
            
        except Exception as e:
            logger.debug(f"Erreur test date {timestamp_to_datetime_str(test_date)} pour {symbol}: {e}")
            continue
    
    logger.warning(f"Impossible de déterminer la date de listing pour {symbol}")
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
    logger.info(f"🚀 Début backfill pour {symbol}")
    
    now = int(time.time())
    interval_sec = 60
    total_inserted = 0

    async with pool.acquire() as conn:
        await create_table_if_not_exists(conn, symbol)
        
        # Récupérer le dernier timestamp disponible
        last_ts = await get_last_timestamp(conn, symbol)
        
        if last_ts and last_ts < now:
            # Reprise depuis le dernier timestamp + 1 minute
            start = last_ts + interval_sec
            logger.info(f"📈 Reprise backfill pour {symbol} depuis {timestamp_to_datetime_str(start)}")
        else:
            # Nouveau symbole - trouver la date de listing
            logger.info(f"🔍 Recherche date de listing pour {symbol}")
            listing_date = await get_symbol_listing_date(symbol)
            
            if not listing_date:
                logger.error(f"❌ Impossible de déterminer la date de listing pour {symbol}")
                return
                
            # Commencer depuis la date de listing ou la limite de rétention
            retention_start = now - days * 24 * 3600
            start = max(listing_date, retention_start)
            
            logger.info(f"📅 Backfill complet pour {symbol} depuis {timestamp_to_datetime_str(start)}")
            
            # Nettoyer les anciennes données pour un backfill complet
            await clean_old_data(conn, symbol, days)

    # Vérification de sécurité
    if start >= now:
        logger.warning(f"⚠️ Start timestamp {timestamp_to_datetime_str(start)} est dans le futur pour {symbol}")
        return

    current_start = start
    consecutive_failures = 0
    
    while current_start < now and consecutive_failures < 5:
        # Limiter la fin du chunk au timestamp actuel
        current_end = min(current_start + CHUNK_SIZE_SECONDS, now - 60)  # -60s de marge
        
        # Si le chunk est trop petit, on s'arrête
        if current_end <= current_start:
            logger.info(f"⏹️ Chunk trop petit pour {symbol}, arrêt")
            break
            
        logger.info(f"⏳ Traitement {symbol}: {timestamp_to_datetime_str(current_start)} → {timestamp_to_datetime_str(current_end)}")

        batch_start = current_start
        batch_success = False
        
        while batch_start < current_end:
            # Vérification supplémentaire pour éviter les requêtes futures
            if batch_start >= now - 60:  # Marge de 60 secondes
                logger.info(f"⏭️ Approche du temps présent pour {symbol}, arrêt du batch")
                break

            try:
                logger.debug(f"📡 Requête API pour {symbol}: {timestamp_to_datetime_str(batch_start)}")
                data = get_ohlcv(symbol, interval=INTERVAL, limit=LIMIT_PER_REQUEST, startTime=batch_start)
                
                if not data:
                    logger.warning(f"📭 Pas de données pour {symbol} à partir de {timestamp_to_datetime_str(batch_start)}")
                    break

                # Vérifier que les données reçues ne sont pas dans le futur
                latest_data_ts = data[-1][0] // 1000
                if latest_data_ts > now:
                    logger.warning(f"⚠️ Données futures reçues pour {symbol}, filtrage nécessaire")
                    # Filtrer les données futures
                    data = [d for d in data if d[0] // 1000 <= now]

                if data:  # Insérer seulement s'il reste des données après filtrage
                    async with pool.acquire() as conn:
                        inserted = await insert_ohlcv_batch(conn, symbol, interval_sec, data)
                        total_inserted += inserted

                batch_success = True
                consecutive_failures = 0

                # Calculer le prochain batch_start
                if data:
                    last_ts_ms = data[-1][0]
                    last_ts_sec = last_ts_ms // 1000
                    batch_start = last_ts_sec + interval_sec
                else:
                    break

                # Si on reçoit moins de données que demandé, on a atteint la fin
                if len(data) < LIMIT_PER_REQUEST:
                    logger.info(f"📊 Fin des données disponibles pour {symbol}")
                    break

                # Rate limiting
                await asyncio.sleep(API_RATE_LIMIT_DELAY)
                
            except Exception as e:
                logger.error(f"❌ Erreur lors du traitement de {symbol}: {e}")
                consecutive_failures += 1
                await asyncio.sleep(RETRY_DELAY * consecutive_failures)
                break

        if not batch_success:
            consecutive_failures += 1
            logger.warning(f"⚠️ Échec batch pour {symbol}, tentatives échouées: {consecutive_failures}")
            # Essayer de passer au chunk suivant même après échec
        
        current_start = current_end

    logger.info(f"✅ Backfill terminé pour {symbol}, total inséré: {total_inserted}")

async def main():
    """Fonction principale"""
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
        
        # Traiter les symboles séquentiellement pour éviter les rate limits
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"🔄 Progression: {i}/{len(symbols)} - Traitement de {symbol}")
            try:
                await backfill_symbol(pool, symbol, RETENTION_DAYS)
                # Pause entre les symboles
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