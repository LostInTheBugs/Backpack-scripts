import os
import pandas as pd
import asyncio
from datetime import datetime, timezone, timedelta
from utils.logger import log
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s

def load_ohlcv_from_db(symbol: str, lookback_seconds=3600) -> pd.DataFrame:
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
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Remplacer les NaN initiaux par la première valeur non-NaN
    first_valid_idx = df['rsi'].first_valid_index()
    if first_valid_idx is not None:
        df['rsi'].fillna(method='bfill', inplace=True)
        log(f"[{symbol}] RSI premiers NaN remplacés par backward fill à partir de l'index {first_valid_idx}", level="DEBUG")

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
    Si df est None, charge les données depuis la base PostgreSQL pour le symbole donné.
    """
    if df is None:
        if symbol is None:
            raise ValueError("Le paramètre symbol doit être fourni si df est None")
        log(f"[{symbol}] Chargement des données OHLCV depuis la base...", level="INFO")
        df = load_ohlcv_from_db(symbol)
        if df is None or df.empty:
            raise ValueError(f"[{symbol}] Aucune donnée OHLCV disponible en base.")

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
        df = df_rsi  # mise à jour df avec RSI
        log(f"[{symbol}] ✅ RSI calculé avec succès.", level="INFO")
    else:
        log(f"[{symbol}] [WARNING] RSI non calculé (données insuffisantes ou NaN permanents).", level="INFO")

    df = calculate_trix(df)
    df = calculate_breakout_levels(df)

    return df
