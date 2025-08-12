import asyncio
from datetime import datetime, timezone, timedelta
from ScriptDatabase.pgsql_ohlcv import table_name_from_symbol
from utils.public import get_ohlcv  # ta fonction API
import asyncpg

BACKFILL_DAYS = 90
INTERVAL = "1m"
LIMIT_PER_CALL = 1000

async def get_last_timestamp(pool, symbol):
    table_name = table_name_from_symbol(symbol)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                f"SELECT timestamp FROM {table_name} ORDER BY timestamp DESC LIMIT 1"
            )
            return row["timestamp"] if row else None
        except Exception:
            return None

async def backfill_symbol(pool, symbol):
    print(f"🔄 Backfill {symbol} pour {BACKFILL_DAYS} jours")

    # Date de départ fixe (exemple) - à adapter si besoin
    fixed_start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)

    # Chercher dernier timestamp en base
    last_ts = await get_last_timestamp(pool, symbol)

    # Si last_ts présent, on commence juste après, sinon on commence à fixed_start_date
    if last_ts is not None:
        start_dt = last_ts + timedelta(minutes=1)
    else:
        start_dt = fixed_start_date

    # Fin = maintenant UTC
    end_dt = datetime.now(timezone.utc)

    # Transformer en timestamp secondes UNIX
    start_ts_sec = int(start_dt.timestamp())
    end_ts_sec = int(end_dt.timestamp())

    current_start = start_ts_sec

    while current_start < end_ts_sec:
        try:
            data = get_ohlcv(
                symbol,
                interval=INTERVAL,
                limit=LIMIT_PER_CALL,
                startTime=current_start,
            )
            if not data:
                print(f"❌ Pas de données pour {symbol} à partir de {datetime.fromtimestamp(current_start, timezone.utc)}")
                break

            # Transformation et insertion en base (à adapter selon ta fonction d’insertion)
            # Par exemple construire un DataFrame et insérer via asyncpg copy ou execute batch
            
            # Ici, on avance la fenêtre : next start = timestamp de dernière bougie + interval
            last_candle_ts_ms = data[-1][0]  # timestamp en ms (selon API)
            current_start = int(last_candle_ts_ms / 1000) + 60  # +60 sec pour 1m interval

            print(f"✅ Données récupérées pour {symbol} jusqu’à {datetime.fromtimestamp(current_start, timezone.utc)}")

        except Exception as e:
            print(f"[ERROR] Backfill {symbol}: {e}")
            break

async def main():
    pool = await asyncpg.create_pool(dsn=os.environ["PG_DSN"])

    symbols = ["BTC_USDC_PERP", "ETH_USDC_PERP", "SOL_USDC_PERP"]  # ou charger ta liste dynamiquement

    for symbol in symbols:
        await backfill_symbol(pool, symbol)

    await pool.close()

if __name__ == "__main__":
    import os, asyncio
    asyncio.run(main())
