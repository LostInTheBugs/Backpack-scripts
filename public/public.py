import requests

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 20):
    """
    Récupère les bougies OHLCV depuis Backpack Exchange.

    symbol: 'BTC_USDC' (underscore)
    """
    url = f"https://api.backpack.exchange/api/v1/markets/{symbol}/candles"
    params = {"interval": interval, "limit": limit}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "timestamp": int(c["startTime"]),
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": float(c["volume"]),
        }
        for c in data
    ]
