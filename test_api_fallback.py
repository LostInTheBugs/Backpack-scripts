import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from bpx.public import Public

public = Public()

async def fetch_ohlcv_from_api_sdk(symbol: str, interval: str, start_time: int, end_time: int) -> pd.DataFrame:
    try:
        data = public.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time * 1000,
            end_time=end_time * 1000,
        )
        if not data:
            print(f"[{symbol}] Pas de données reçues")
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_asset_volume","number_of_trades",
            "taker_buy_base_asset_volume","taker_buy_quote_asset_volume","ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df[["timestamp","open","high","low","close","volume"]]
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        print(f"[{symbol}] Erreur fetch API SDK: {e}")
        return pd.DataFrame()

async def fetch_api_fallback(symbol: str) -> pd.DataFrame | None:
    interval_sec = 60
    total_minutes = 14 * 24 * 60 + 100  # 14 jours + marge
    end_time = int(datetime.now(timezone.utc).timestamp())
    start_time = end_time - total_minutes * interval_sec
    df_total = pd.DataFrame()

    while start_time < end_time:
        batch_end = min(start_time + 1000 * interval_sec, end_time)
        df_batch = await fetch_ohlcv_from_api_sdk(symbol, "1m", start_time, batch_end)
        if df_batch.empty:
            break
        df_total = pd.concat([df_total, df_batch])
        start_time = batch_end + 1

    if df_total.empty:
        print(f"[{symbol}] Aucun donnée récupérée via API fallback")
        return None

    df_total = df_total.drop_duplicates(subset=["timestamp"])
    df_total = df_total.sort_values("timestamp").reset_index(drop=True)
    return df_total

async def main():
    symbol = "BTC_USDC_PERP"
    df = await fetch_api_fallback(symbol)
    if df is not None:
        print(f"[{symbol}] Données récupérées via API fallback: {len(df)} lignes")
        print(df.tail(5))
    else:
        print(f"[{symbol}] Échec récupération données fallback")

if __name__ == "__main__":
    asyncio.run(main())
