import os
import pandas as pd
import asyncio
import requests
from datetime import datetime, timezone, timedelta
from utils.logger import log
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s

# Définir la période RSI en minutes (14 jours par défaut)
RSI_PERIOD_MINUTES = 14 * 24 * 60

def load_ohlcv_from_db(symbol: str, lookback_seconds=6*3600) -> pd.DataFrame:
    """
    Charge les données OHLCV 1s depuis PostgreSQL pour le symbole donné,
    sur une fenêtre de lookback_seconds en arrière à partir de maintenant.
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

def fetch_ohlcv_from_api(symbol: str, interval: str = "1m", limit: int = 1000, startTime: int = None, endTime: int = None) -> pd.DataFrame:
    """
    Récupère les données OHLCV depuis l'API Backpack Exchange.
    startTime et endTime doivent être des timestamps UNIX en secondes (int).
    """
    url = "https://api.backpack.exchange/api/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if startTime is not None:
        # Vérification simple pour éviter double multiplication
        if startTime > 1e12:  # On dirait déjà un ms timestamp, on convertit en secondes
            startTime = startTime // 1000
        params["startTime"] = int(startTime * 1000)
    if endTime is not None:
        if endTime > 1e12:
            endTime = endTime // 1000
        params["endTime"] = int(endTime * 1000)

    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=["timestamp","open","high","low","close","volume","close_time","quote_asset_volume","number_of_trades","taker_buy_base_asset_volume","taker_buy_quote_asset_volume","ignore"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df[["timestamp","open","high","low","close","volume"]]
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        log(f"[{symbol}] [ERROR] fetch_ohlcv_from_api: {e}", level="ERROR")
        return pd.DataFrame()


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

    rsi = rsi.fillna(method='bfill')  # remplace les NaN initiaux

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
    Si df est None, charge les données depuis la base PostgreSQL pour le symbole donné,
    puis fallback sur l'API si données insuffisantes.
    """
    if df is None:
        if symbol is None:
            raise ValueError("Le paramètre symbol doit être fourni si df est None")
        log(f"[{symbol}] Chargement des données OHLCV depuis la base...", level="INFO")
        df = load_ohlcv_from_db(symbol)
        if df is None or df.empty:
            log(f"[{symbol}] Aucune donnée en base, tentative via API...", level="WARNING")
            df = fetch_ohlcv_from_api(symbol, interval="1m", limit=1000)
            if df.empty:
                raise ValueError(f"[{symbol}] Impossible de récupérer des données via l'API")
        elif len(df) < RSI_PERIOD_MINUTES:
            log(f"[{symbol}] Données insuffisantes en base ({len(df)} lignes), fallback sur API...", level="WARNING")
            start_ts = int((datetime.now(timezone.utc) - timedelta(days=14)).timestamp())
            df_api = fetch_ohlcv_from_api(symbol, interval="1m", limit=1000, startTime=start_ts)
            if not df_api.empty:
                df = df_api
            else:
                log(f"[{symbol}] Fallback API a échoué, utilisation des données en base limitées", level="WARNING")

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

    df_rsi = calculate_rsi(df, period=14, symbol=symbol)
    if df_rsi is not None:
        df = df_rsi
        log(f"[{symbol}] ✅ RSI calculé avec succès.", level="INFO")
    else:
        log(f"[{symbol}] [WARNING] RSI non calculé (données insuffisantes ou NaN permanents).", level="INFO")

    df = calculate_trix(df)
    df = calculate_breakout_levels(df)

    return df
