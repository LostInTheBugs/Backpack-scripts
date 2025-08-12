import os
import pandas as pd
import asyncio
from datetime import datetime, timezone, timedelta
from utils.logger import log
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from bpx.public import Public

public = Public()

# Période RSI configurée (14 jours * 24h * 60m) - adapter si besoin
RSI_PERIOD_MINUTES = 14 * 24 * 60

def load_ohlcv_from_db(symbol: str, lookback_seconds=6*3600) -> pd.DataFrame:
    """
    Charge les données OHLCV 1s depuis PostgreSQL pour le symbole donné,
    sur une fenêtre lookback_seconds en arrière à partir de maintenant.
    """
    async def _load_async():
        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=lookback_seconds)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
        return df

    try:
        df = asyncio.run(_load_async())
        if df.empty:
            log(f"[{symbol}] [WARNING] Pas de données chargées depuis la base.", level="WARNING")
            return None
        return df
    except Exception as e:
        log(f"[{symbol}] [ERROR] Erreur chargement base de données : {e}", level="ERROR")
        return None

async def fetch_ohlcv_chunk(symbol: str, start_time: int, end_time: int) -> pd.DataFrame:
    """
    Récupère un chunk OHLCV via SDK Backpack entre start_time et end_time (timestamps en secondes UTC).
    """
    try:
        data = await asyncio.to_thread(
            public.get_klines,
            symbol=symbol,
            interval="1m",
            start_time=start_time,
            end_time=end_time
        )
        if not data:
            log(f"[{symbol}] Pas de données reçues entre {start_time} et {end_time}", level="WARNING")
            return pd.DataFrame()

        # La data est liste de listes, colonne timestamp en ms
        df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume",
                                        "close_time","quote_asset_volume","number_of_trades",
                                        "taker_buy_base_asset_volume","taker_buy_quote_asset_volume","ignore"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df[["timestamp","open","high","low","close","volume"]]
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        log(f"[{symbol}] [ERROR] fetch_ohlcv_chunk: {e}", level="ERROR")
        return pd.DataFrame()

async def fetch_api_fallback(symbol: str) -> pd.DataFrame | None:
    """
    Récupère au moins RSI_PERIOD_MINUTES de données via API Backpack en batchs de 1000 bougies max (en découpant par chunks de 6h).
    Ici on élargit la période de récupération pour avoir assez de données pour RSI 14 jours.
    """
    interval_sec = 60
    total_minutes = RSI_PERIOD_MINUTES * 4  # multiplication x4 pour s'assurer assez de données
    end_time = int(datetime.now(timezone.utc).timestamp())
    start_time = end_time - total_minutes * interval_sec

    chunk_seconds = 6 * 3600  # chunks de 6h
    df_total = pd.DataFrame()

    current_start = start_time
    while current_start < end_time:
        current_end = min(current_start + chunk_seconds, end_time)
        df_chunk = await fetch_ohlcv_chunk(symbol, current_start, current_end)
        if df_chunk.empty:
            log(f"[{symbol}] Aucune donnée pour chunk {current_start}-{current_end}, arrêt fallback API.", level="WARNING")
            break
        df_total = pd.concat([df_total, df_chunk])
        current_start = current_end + 1
        await asyncio.sleep(0.25)  # anti rate limit

    if df_total.empty:
        log(f"[{symbol}] [WARNING] Pas de données récupérées via API fallback", level="WARNING")
        return None

    df_total = df_total.drop_duplicates(subset=["timestamp"])
    df_total = df_total.sort_values("timestamp").reset_index(drop=True)
    return df_total

def calculate_macd(df, fast=12, slow=26, signal=9, symbol="UNKNOWN"):
    df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    log(f"[{symbol}] ✅ MACD calculé automatiquement.", level="INFO")
    return df

def calculate_rsi(df, period=14, symbol="UNKNOWN"):
    if len(df) < period:
        log(f"[{symbol}] [WARNING] Pas assez de données pour RSI ({len(df)} < {period}), signal ignoré.", level="DEBUG")
        return None

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    rsi = rsi.bfill()  # méthode explicite futur-proof

    df['rsi'] = rsi

    first_valid_idx = df['rsi'].first_valid_index()
    if first_valid_idx is not None:
        log(f"[{symbol}] RSI recalculé avec ewm, premiers NaN remplacés par backward fill à partir de l'index {first_valid_idx}", level="DEBUG")

    return df

def calculate_trix(df, period=9):
    ema1 = df['close'].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    df['trix'] = ema3.pct_change() * 100
    return df

def calculate_breakout_levels(df, window=20):
    df['high_breakout'] = df['high'].rolling(window=window).max()
    df['low_breakout'] = df['low'].rolling(window=window).min()
    return df

def compute_all(df=None, symbol=None):
    """
    Calcule tous les indicateurs pour le df fourni.
    Si df est None, charge les données depuis la base PostgreSQL ou fallback API si insuffisant.
    """
    if df is None:
        if symbol is None:
            raise ValueError("Le paramètre symbol doit être fourni si df est None")
        log(f"[{symbol}] Chargement des données OHLCV depuis la base...", level="INFO")
        df = load_ohlcv_from_db(symbol)
        if df is None or df.empty or len(df) < RSI_PERIOD_MINUTES:
            log(f"[{symbol}] Données insuffisantes en base ({0 if df is None else len(df)} lignes), fallback sur API...", level="WARNING")
            df = asyncio.run(fetch_api_fallback(symbol))
            if df is None:
                raise ValueError(f"[{symbol}] Impossible de récupérer des données via API fallback")

    df = df.copy()

    # Déduire symbole si besoin
    if symbol is None:
        if 'symbol' in df.columns and not df['symbol'].empty:
            symbol = str(df['symbol'].iloc[0])
        elif hasattr(df, 'attrs') and 'symbol' in df.attrs:
            symbol = df.attrs['symbol']
        else:
            symbol = "UNKNOWN"

    df = calculate_macd(df, symbol=symbol)

    df_rsi = calculate_rsi(df, symbol=symbol)
    if df_rsi is not None:
        df = df_rsi
        log(f"[{symbol}] ✅ RSI calculé avec succès.", level="INFO")
    else:
        log(f"[{symbol}] [WARNING] RSI non calculé (données insuffisantes ou NaN permanents).", level="INFO")

    df = calculate_trix(df)
    df = calculate_breakout_levels(df)

    return df
