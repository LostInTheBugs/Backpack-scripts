import asyncio
from datetime import datetime, timedelta, timezone
import asyncpg
import pandas as pd
from utils.public import get_ohlcv, format_table_name  # ta fonction existante

PG_DSN = "ton_dsn_ici"  # ou depuis variable d'env

BACKFILL_DAYS = 90
INTERVAL = "1m"
LIMIT_PER_CALL = 1000  # max points par requête (à ajuster selon API)

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
    # Optionnel : hypertable timescale
    try:
        await conn.execute(f"SELECT create_hypertable('{table_name}', 'timestamp', if_not_exists => TRUE);")
    except Exception as e:
        print(f"⚠️ Erreur création hypertable pour {table_name}: {e}")

async def insert_ohlcv_batch(conn, symbol, df):
    table_name = format_table_name(symbol)
    interval_sec = 60  # 1m = 60 sec
    records = []
    for idx, row in df.iterrows():
        dt = pd.to_datetime(row["open_time"], unit='ms', utc=True)
        records.append((
            symbol,
            dt,
            interval_sec,
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"]
        ))

    query = f"""
        INSERT INTO {table_name} (symbol, timestamp, interval_sec, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (symbol, interval_sec, timestamp) DO NOTHING
    """
    await conn.executemany(query, records)
    print(f"⏳ {len(records)} bougies insérées pour {symbol}.")

async def backfill_symbol(pool, symbol):
    print(f"🔄 Backfill {symbol} pour {BACKFILL_DAYS} jours")
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=BACKFILL_DAYS)
    start_ts_sec = int(start_time.timestamp())
    end_ts_sec = int(now.timestamp())

    async with pool.acquire() as conn:
        await create_table_if_not_exists(conn, symbol)

    current_start = start_ts_sec
    while current_start < end_ts_sec:
        # Appeler ta fonction get_ohlcv (synchrone) avec interval='1m', limit=LIMIT_PER_CALL, startTime=current_start
        data = get_ohlcv(symbol, interval=INTERVAL, limit=LIMIT_PER_CALL, startTime=current_start)
        if not data:
            print(f"❌ Pas de données pour {symbol} à partir de {datetime.fromtimestamp(current_start)}")
            break

        # data est une liste de listes (open_time, open, high, low, close, volume, ...)
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume", "ignore"
        ])

        # Convertir colonnes en bonnes types float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        async with pool.acquire() as conn:
            await insert_ohlcv_batch(conn, symbol, df)

        # Passer au timestamp suivant : open_time max + 60 secondes
        last_open_time_ms = df["open_time"].max()
        current_start = int(last_open_time_ms / 1000) + 60

        # Si moins de LIMIT_PER_CALL résultats, fin de boucle (données à jour)
        if len(df) < LIMIT_PER_CALL:
            break

async def main():
    pool = await asyncpg.create_pool(dsn=PG_DSN)
    symbols = ["BTC_USDC_PERP", "ETH_USDC_PERP", "SOL_USDC_PERP"]  # Par exemple, ou charger dynamiquement

    for symbol in symbols:
        await backfill_symbol(pool, symbol)

    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
