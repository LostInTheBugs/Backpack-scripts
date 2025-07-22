import asyncio
import json
import websockets
import asyncpg
from datetime import datetime, timezone
import os

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

INTERVAL_SEC = 1  # durée de la bougie en secondes

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
        # Arrondir au multiple inférieur de interval_sec
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
            # Bougie en cours, mettre à jour
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price
            self.volume += size
        else:
            # Nouveau bucket : insérer la bougie précédente
            await self.insert_ohlcv(pool, self.current_bucket)

            # Reset pour nouvelle bougie
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
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ohlcv(symbol, interval_sec, timestamp, open, high, low, close, volume)
                VALUES($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, interval_sec, timestamp) DO NOTHING
            """, self.symbol, self.interval_sec, dt, self.open, self.high, self.low, self.close, self.volume)
            print(f"⏳ Bougie insérée {dt} {self.symbol} O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume}")

async def main():
    symbol = "BTC_USDC_PERP"  # adapte ici ou passe en argument
    ws_url = "wss://ws.backpack.exchange"

    aggregator = OHLCVAggregator(symbol, INTERVAL_SEC)
    pool = await asyncpg.create_pool(dsn=PG_DSN)

    async with websockets.connect(ws_url) as ws:
        # Subscribe to trades for the symbol
        sub_msg = {
            "method": "SUBSCRIBE",
            "params": [f"trade.{symbol}"],
            "id": 1,
        }
        await ws.send(json.dumps(sub_msg))
        print(f"✅ Subscribed to trade.{symbol}")

        async for message in ws:
            msg = json.loads(message)
            data = msg.get("data")
            if data and "p" in data and "q" in data and "T" in data:
                price = float(data["p"])
                size = float(data["q"])
                timestamp_ms = int(data["T"])

                await aggregator.process_trade(price, size, timestamp_ms, pool)

if __name__ == "__main__":
    asyncio.run(main())
