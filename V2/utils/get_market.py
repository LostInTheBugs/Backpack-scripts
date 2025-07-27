import requests

def get_market(symbol):
    url = f"https://api.backpack.exchange/api/v1/market/{symbol}"  # ← endpoint corrigé
    response = requests.get(url)

    if response.status_code == 404:
        print(f"⚠️ Marché {symbol} non trouvé (404)")
        return None

    response.raise_for_status()
    return response.json()
