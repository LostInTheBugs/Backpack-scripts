import requests

def list_valid_symbols():
    url = "https://api.backpack.exchange/v1/markets"
    response = requests.get(url)
    response.raise_for_status()
    markets = response.json()

    for market in markets:
        print(f"{market['symbol']:20} | {market['marketType']:6} | {market['orderBookState']:10}")

list_valid_symbols()