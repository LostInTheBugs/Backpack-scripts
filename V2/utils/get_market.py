# public/get_market.py

import requests

def get_market(symbol: str):
    url = f"https://api.backpack.exchange/v1/market/{symbol}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()
