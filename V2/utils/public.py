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

