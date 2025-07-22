import requests

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 20):
    url = "https://api.backpack.exchange/api/v1/market/candles"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP {resp.status_code} pour l'URL {resp.url}")
        raise e
