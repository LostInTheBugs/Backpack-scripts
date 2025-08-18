# indicators/combined_indicators.py (version modifiée)
import os
import pandas as pd
import asyncio
from datetime import datetime, timezone, timedelta
from utils.logger import log
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from bpx.public import Public
from indicators.rsi_calculator import get_cached_rsi

public = Public()

def calculate_macd(df, fast=12, slow=26, signal=9, symbol="UNKNOWN"):
    df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    log(f"[{symbol}] ✅ MACD calculé automatiquement.", level="DEBUG")
    return df

async def calculate_rsi_api(df, symbol="UNKNOWN"):
    """
    Utilise l'API Backpack pour obtenir le RSI au lieu du calcul local
    """
    try:
        rsi_value = await get_cached_rsi(symbol, interval="5m")
        df['rsi'] = rsi_value  # Assigne la même valeur à toute la série
        log(f"[{symbol}] ✅ RSI récupéré via API: {rsi_value:.2f}", level="DEBUG")
        return df
    except Exception as e:
        log(f"[{symbol}] ⚠️ Erreur RSI API, valeur neutre utilisée: {e}", level="WARNING")
        df['rsi'] = 50.0  # Valeur neutre
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

async def compute_all(df=None, symbol=None):
    """
    Version asynchrone avec RSI via API Backpack.
    Calcule tous les indicateurs pour le df fourni.
    """
    if df is None:
        if symbol is None:
            raise ValueError("Le paramètre symbol doit être fourni si df est None")
        log(f"[{symbol}] Chargement des données OHLCV depuis la base...", level="INFO")
        df = load_ohlcv_from_db(symbol)
        if df is None or df.empty:
            raise ValueError(f"[{symbol}] Impossible de récupérer des données")

    df = df.copy()

    # Déduire symbole si besoin
    if symbol is None:
        if 'symbol' in df.columns and not df['symbol'].empty:
            symbol = str(df['symbol'].iloc[0])
        elif hasattr(df, 'attrs') and 'symbol' in df.attrs:
            symbol = df.attrs['symbol']
        else:
            symbol = "UNKNOWN"

    # Calculs des indicateurs
    df = calculate_macd(df, symbol=symbol)
    df = await calculate_rsi_api(df, symbol=symbol)
    df = calculate_trix(df)
    df = calculate_breakout_levels(df)

    return df

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
            log(f"[{symbol}] Pas de données chargées depuis la base.", level="WARNING")
            return None
        return df
    except Exception as e:
        log(f"[{symbol}] Erreur chargement base de données : {e}", level="ERROR")
        return None