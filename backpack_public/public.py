import requests
from datetime import datetime
import requests
import time
import numpy as np
import pandas as pd

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 21, startTime: int = None):
    base_url = "https://api.backpack.exchange/api/v1/klines"
    
    if startTime is None:
        # Par défaut : récupérer les dernières `limit` bougies 1m, donc startTime = now - limit*60s
        startTime = int(time.time()) - limit * 60
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "startTime": startTime
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as e:
        print(f"[ERROR] get_ohlcv(): {e}")
        return None

def get_perp_symbols():
    url = "https://api.backpack.exchange/api/v1/markets"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        perp_symbols = [m['symbol'] for m in markets if 'PERP' in m['symbol']]
        return perp_symbols
    except Exception as e:
        log(f"Erreur récupération symbols PERP: {e}")
        return []

def select_symbols_by_volatility(min_volume=1000, top_n=15, lookback=500):
    perp_symbols = get_perp_symbols()
    vol_list = []
    log(f"Calcul des volatilités pour {len(perp_symbols)} symbols PERP...")

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
            log(f"Erreur sur {symbol}: {e}")

    vol_list.sort(key=lambda x: x[1], reverse=True)
    selected = vol_list[:top_n]

    log(f"Symbols sélectionnés (top {top_n} par volatilité et volume > {min_volume}):")
    for sym, vol, volm in selected:
        log(f"{sym} - Volatilité: {vol:.4f}, Volume moyen: {volm:.0f}")

    return [x[0] for x in selected]