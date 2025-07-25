import time 
import argparse
import os
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import numpy as np
import requests

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.public import get_ohlcv

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20
RESELECT_INTERVAL_SEC = 300  # 5 minutes
TRAILING_STOP_PCT = 0.003  # Stop suiveur un peu plus serré
DEBUG_INDICATORS = True    # Active les logs détaillés des indicateurs

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def prepare_ohlcv_df(ohlcv):
    df = pd.DataFrame(ohlcv)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df


def calculate_macd_rsi(df):
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['rsi'] = ta.rsi(df['close'], length=14)
    return df


def combined_signal(df):
    breakout = breakout_signal(df.to_dict('records'))
    macd_hist = df['MACDh_12_26_9'].iloc[-1]
    rsi = df['rsi'].iloc[-1]

    if DEBUG_INDICATORS:
        print(f"📉 Indicateurs: RSI={rsi:.2f}, MACDh={macd_hist:.5f}, Breakout={breakout}")

    # Allègement des conditions
    macd_bull = macd_hist > 0
    macd_bear = macd_hist < 0

    if breakout == "BUY" and macd_bull and rsi < 60:
        return "BUY"
    elif breakout == "SELL" and macd_bear and rsi > 40:
        return "SELL"
    else:
        return None



def get_perp_symbols():
    url = "https://api.backpack.exchange/api/v1/markets"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        return [m['symbol'] for m in markets if 'PERP' in m['symbol']]
    except Exception as e:
        log(f"Erreur récupération symbols PERP: {e}")
        return []


def select_symbols_by_volatility(min_volume=1000, top_n=15, lookback=500):
    perp_symbols = get_perp_symbols()
    vol_list = []
    log(f"🔎 Calcul des volatilités pour {len(perp_symbols)} symbols PERP...")

    for symbol in perp_symbols:
        try:
            ohlcv = get_ohlcv(symbol, interval='1h', limit=lookback)
            if not ohlcv or len(ohlcv) < 30:
                continue
            df = prepare_ohlcv_df(ohlcv)
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            volatility = df['log_return'].std() * np.sqrt(24 * 365)
            avg_volume = df['volume'].mean()
            if avg_volume < min_volume:
                continue
            vol_list.append((symbol, volatility, avg_volume))
        except Exception as e:
            log(f"⚠️ Erreur sur {symbol}: {e}")

    vol_list.sort(key=lambda x: x[1], reverse=True)
    selected = vol_list[:top_n]

    log(f"✅ Symbols sélectionnés (top {top_n} par volatilité et volume > {min_volume}):")
    for sym, vol, volm in selected:
        log(f"• {sym} - Volatilité: {vol:.4f}, Volume moyen: {volm:.0f}")

    return [x[0] for x in selected]
