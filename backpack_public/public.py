import requests
from datetime import datetime

def get_ohlcv_coingecko(symbol: str, interval: str = "1m", limit: int = 20):
    # CoinGecko ne fait pas USDC par défaut, mais USDT est proche
    # symbol = "bitcoin" for BTC, interval en minutes, limit = nb de points

    coin_id = "bitcoin" if "BTC" in symbol else "ethereum"  # simplification
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {
        "vs_currency": "usd",
        "days": 1,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()  # liste de [timestamp, open, high, low, close]

    # Convertir timestamp ms en dict standardisé et limiter la taille
    candles = []
    for c in data[-limit:]:
        candles.append({
            "timestamp": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": 0,  # CoinGecko ne fournit pas volume ici
        })
    return candles
