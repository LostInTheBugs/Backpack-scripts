import requests
from datetime import datetime

def get_ohlcv(symbol="BTC-USDC", interval="1m", limit=100):
    """
    Récupère les chandeliers (OHLCV) depuis l'API publique Backpack Exchange.

    :param symbol: str, ex: 'BTC-USDC'
    :param interval: str, ex: '1m', '5m', '1h', '1d'
    :param limit: int, nombre de bougies à récupérer (max: 1000 si dispo)
    :return: liste de dictionnaires avec timestamp, open, high, low, close, volume
    """
    url = "https://api.backpack.exchange/api/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        klines = resp.json()
        
        parsed = []
        for k in klines:
            parsed.append({
                "timestamp": datetime.utcfromtimestamp(k["t"] / 1000),
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
                "volume": float(k["v"]),
                "trades": k.get("n", None)  # nombre de trades si dispo
            })

        return parsed

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] get_ohlcv(): {e}")
        return []
