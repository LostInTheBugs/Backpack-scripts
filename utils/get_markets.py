import requests

def list_valid_symbols():
    url = "https://api.backpack.exchange/api/v1/markets"  # ← nouvelle URL
    response = requests.get(url)
    response.raise_for_status()
    markets = response.json()

    for market in markets:
        symbol = market.get("symbol")
        market_type = market.get("marketType")
        state = market.get("orderBookState")
        print(f"{symbol:20} | {market_type:6} | {state:10}")

list_valid_symbols()
