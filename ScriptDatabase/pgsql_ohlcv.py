import asyncio
import json
import websockets
import asyncpg
import pandas as pd
from datetime import datetime, timezone, timedelta
from utils.logger import log
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

INTERVAL_SEC = 1
SYMBOLS_FILE = "symbol.lst"
RETENTION_DAYS = 90

def table_name_from_symbol(symbol: str) -> str:
    return "ohlcv_" + symbol.lower().replace("_", "__")

async def fetch_ohlcv_1s(symbol: str, start_ts: datetime, end_ts: datetime, pool=None) -> pd.DataFrame:
    """
    Récupère les bougies 1s de la base PostgreSQL entre start_ts et end_ts pour symbol donné.
    """
    table_name = "ohlcv_" + symbol.lower().replace("_", "__")

    query = f"""
    SELECT timestamp, open, high, low, close, volume
    FROM {table_name}
    WHERE interval_sec = 1
      AND timestamp >= $1
      AND timestamp <= $2
    ORDER BY timestamp ASC
    """

    if pool is None:
        pool = await asyncpg.create_pool(dsn=PG_DSN)
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, start_ts, end_ts)
        await pool.close()
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, start_ts, end_ts)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df

async def create_table_if_not_exists(conn, symbol):
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
    try:
        await conn.execute(f"SELECT create_hypertable('{table_name}', 'timestamp', if_not_exists => TRUE);")
    except Exception as e:
        log(f"⚠️ Erreur création hypertable pour {table_name}: {e}", level="ERROR")

async def delete_old_data(conn, symbol, retention_days=RETENTION_DAYS):
    table_name = table_name_from_symbol(symbol)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await conn.execute(f"DELETE FROM {table_name} WHERE timestamp < $1;", cutoff)
    log(f"🗑️ Suppression données > {retention_days} jours dans {table_name} : {result}", level="INFO")

class OHLCVAggregator:
    def __init__(self, symbol, interval_sec):
        self.symbol = symbol
        self.interval_sec = interval_sec
        self.current_bucket = None
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.volume = 0.0

    def _get_bucket_start(self, timestamp):
        return timestamp - (timestamp % self.interval_sec)

    async def process_trade(self, price: float, size: float, timestamp_ms: int, pool):
        ts = timestamp_ms // 1000
        bucket = self._get_bucket_start(ts)

        if self.current_bucket is None:
            self.current_bucket = bucket
            self.open = price
            self.high = price
            self.low = price
            self.close = price
            self.volume = size
        elif bucket == self.current_bucket:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price
            self.volume += size
        else:
            await self.insert_ohlcv(pool, self.current_bucket)
            self.current_bucket = bucket
            self.open = price
            self.high = price
            self.low = price
            self.close = price
            self.volume = size

    async def insert_ohlcv(self, pool, bucket_start):
        if bucket_start > 10**12:
            bucket_start = bucket_start // 1000
        dt = datetime.fromtimestamp(bucket_start, tz=timezone.utc)

        table_name = table_name_from_symbol(self.symbol)
        async with pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {table_name} (symbol, timestamp, interval_sec, open, high, low, close, volume)
                VALUES($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, interval_sec, timestamp) DO NOTHING
            """, self.symbol, dt, self.interval_sec, self.open, self.high, self.low, self.close, self.volume)

            log(f"⏳ Bougie insérée {dt} {self.symbol} O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume}", level="DEBUG")

async def subscribe_and_aggregate(symbol: str, pool, stop_event: asyncio.Event):
    ws_url = "wss://ws.backpack.exchange"
    aggregator = OHLCVAggregator(symbol, INTERVAL_SEC)

    while not stop_event.is_set():
        try:
            async with websockets.connect(ws_url) as ws:
                sub_msg = {
                    "method": "SUBSCRIBE",
                    "params": [f"trade.{symbol}"],
                    "id": 1,
                }
                await ws.send(json.dumps(sub_msg))
                log(f"✅ Subscribed to trade.{symbol}", level="INFO")

                while not stop_event.is_set():
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=10)
                    except asyncio.TimeoutError:
                        continue
                    msg = json.loads(message)
                    data = msg.get("data")
                    if data and "p" in data and "q" in data and "T" in data:
                        price = float(data["p"])
                        size = float(data["q"])
                        timestamp_ms = int(data["T"])
                        await aggregator.process_trade(price, size, timestamp_ms, pool)

        except (websockets.ConnectionClosed, asyncio.CancelledError):
            log(f"🔴 WebSocket closed for {symbol}", level="ERROR")
            if stop_event.is_set():
                break
            log(f"♻️ Tentative de reconnexion pour {symbol} dans 5 secondes...", level="DEBUG")
            await asyncio.sleep(5)
        except Exception as e:
            log(f"❌ Erreur websocket {symbol}: {e}", level="ERROR")
            log(f"♻️ Tentative de reconnexion pour {symbol} dans 5 secondes...", level="DEBUG")
            await asyncio.sleep(5)

async def periodic_cleanup(pool, get_symbols_func, retention_days=RETENTION_DAYS):
    while True:
        symbols = await get_symbols_func()
        async with pool.acquire() as conn:
            for symbol in symbols:
                await delete_old_data(conn, symbol, retention_days)
        await asyncio.sleep(24 * 3600)  # 24h

async def fetch_all_symbols() -> list[str]:
    import aiohttp

    url = "https://api.backpack.exchange/api/v1/tickers"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log(f"[ERROR] ❌ Erreur API Backpack : HTTP {resp.status}", level="ERROR")
                    return []
                data = await resp.json()
    except Exception as e:
        log(f"❌ Exception lors de la récupération des symboles : {e}", level="ERROR")
        return []

    symbols = [t["symbol"] for t in data if "_PERP" in t.get("symbol", "")]
    return symbols

async def monitor_symbols(pool, get_symbols_func):
    current_tasks = {}
    known_symbols = set()  # mémoriser TOUS les symboles vus

    while True:
        new_api_symbols = set(await get_symbols_func())
        # On ajoute les nouveaux symboles à known_symbols
        known_symbols.update(new_api_symbols)

        # Symboles à lancer (présents dans known mais pas encore abonnés)
        to_start = known_symbols - current_tasks.keys()

        # Créer tables si nécessaire
        async with pool.acquire() as conn:
            for sym in to_start:
                await create_table_if_not_exists(conn, sym)

        # Démarrer abonnements pour nouveaux symboles
        for sym in to_start:
            log(f"▶️ Démarrage abonnement {sym}", level="DEBUG")
            stop_event = asyncio.Event()
            task = asyncio.create_task(subscribe_and_aggregate(sym, pool, stop_event))
            current_tasks[sym] = (task, stop_event)

        # Ici, pas d’arrêt d’abonnement automatique

        await asyncio.sleep(60)

def get_ohlcv_1s_sync(symbol: str, start_ts: datetime, end_ts: datetime) -> pd.DataFrame:
    """
    Wrapper synchrone qui appelle la fonction async fetch_ohlcv_1s.
    """
    return asyncio.run(fetch_ohlcv_1s(symbol, start_ts, end_ts))


async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)

    # Lance la surveillance du fichier et la purge
    cleanup_task = asyncio.create_task(periodic_cleanup(pool, fetch_all_symbols))
    monitor_task = asyncio.create_task(monitor_symbols(pool, fetch_all_symbols))
    await asyncio.gather(cleanup_task, monitor_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log(f"\n👋 Arrêt demandé, fin du programme.", level="INFO")
