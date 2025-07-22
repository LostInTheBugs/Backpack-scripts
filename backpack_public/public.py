import requests

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 20):
    url = "https://api.backpack.exchange/api/v1/market/candles"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    data = get_ohlcv("BTC_USDC_PERP")
    print(data[:2])
