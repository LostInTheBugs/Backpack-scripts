import requests

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 20):
    url = f"https://api.backpack.exchange/api/v1/markets/{symbol}/candles"
    params = {"interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return [
        {
            "timestamp": int(candle["start"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle["volume"]),
        }
        for candle in data
    ]
