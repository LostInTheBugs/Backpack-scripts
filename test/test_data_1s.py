from V2.ScriptDatabase.pgsql_ohlcv import get_ohlcv_1s_sync
from datetime import datetime, timedelta

symbol = "DOGE_USDC_PERP"
end_ts = datetime.utcnow()
start_ts = end_ts - timedelta(minutes=5)

df = get_ohlcv_1s_sync(symbol, start_ts, end_ts)

print(df.head())
print(f"{len(df)} bougies récupérées entre {start_ts} et {end_ts}")
