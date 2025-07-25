import asyncio
import json
import websockets
import asyncpg
from datetime import datetime, timezone, timedelta
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

INTERVAL_SEC = 1
SYMBOLS_FILE = "symbol.lst"
RETENTION_DAYS = 90

def table_name_from_symbol(symbol: str) -> str:
    return "ohlcv_" + symbol.lower().replace("_", "__")

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
        print(f"⚠️ Erreur création hypertable pour {table_name}: {e}")

async def delete_old_data(conn, symbol, retention_days=RETENTION_DAYS):
    table_name = table_name_from_symbol(symbol)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await conn.execute(f"DELETE FROM {table_name} WHERE timestamp < $1;", cutoff)
    print(f"🗑️ Suppression données > {retention_days} jours dans {table_name} : {result}")

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

            print(f"⏳ Bougie insérée {dt} {self.symbol} O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume}")

async def subscribe_and_aggregate(symbol: str, pool, stop_event: asyncio.Event):
    ws_url = "wss://ws.backpack.exchange"
    aggregator = OHLCVAggregator(symbol, INTERVAL_SEC)
    try:
        async with websockets.connect(ws_url) as ws:
            sub_msg = {
                "method": "SUBSCRIBE",
                "params": [f"trade.{symbol}"],
                "id": 1,
            }
            await ws.send(json.dumps(sub_msg))
            print(f"✅ Subscribed to trade.{symbol}")

            while not stop_event.is_set():
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    # Ping or reconnect could be done ici si besoin
                    continue
                msg = json.loads(message)
                data = msg.get("data")
                if data and "p" in data and "q" in data and "T" in data:
                    price = float(data["p"])
                    size = float(data["q"])
                    timestamp_ms = int(data["T"])
                    await aggregator.process_trade(price, size, timestamp_ms, pool)
    except (websockets.ConnectionClosed, asyncio.CancelledError):
        print(f"🔴 WebSocket closed for {symbol}")
    except Exception as e:
        print(f"❌ Erreur websocket {symbol}: {e}")

async def periodic_cleanup(pool, get_symbols_func, retention_days=RETENTION_DAYS):
    while True:
        symbols = await get_symbols_func()
        async with pool.acquire() as conn:
            for symbol in symbols:
                await delete_old_data(conn, symbol, retention_days)
        await asyncio.sleep(24 * 3600)  # 24h

async def read_symbols_file() -> list[str]:
    if not os.path.exists(SYMBOLS_FILE):
        print(f"⚠️ Fichier {SYMBOLS_FILE} introuvable")
        return []
    with open(SYMBOLS_FILE, "r") as f:
        symbols = [line.strip() for line in f if line.strip()]
    return symbols

async def monitor_symbols(pool):
    current_tasks = {}
    current_symbols = set()

    while True:
        new_symbols = set(await read_symbols_file())

        # Stop subscriptions for removed symbols
        removed = current_symbols - new_symbols
        for sym in removed:
            print(f"🛑 Arrêt abonnement {sym}")
            task, stop_event = current_tasks.pop(sym)
            stop_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Add subscriptions for new symbols
        added = new_symbols - current_symbols
        async with pool.acquire() as conn:
            for sym in added:
                await create_table_if_not_exists(conn, sym)
        for sym in added:
            print(f"▶️ Démarrage abonnement {sym}")
            stop_event = asyncio.Event()
            task = asyncio.create_task(subscribe_and_aggregate(sym, pool, stop_event))
            current_tasks[sym] = (task, stop_event)

        current_symbols = new_symbols

        await asyncio.sleep(60)  # vérifier toutes les minutes

async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)

    # Lance la surveillance du fichier et la purge
    cleanup_task = asyncio.create_task(periodic_cleanup(pool, read_symbols_file))
    monitor_task = asyncio.create_task(monitor_symbols(pool))

    await asyncio.gather(cleanup_task, monitor_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Arrêt demandé, fin du programme.")
