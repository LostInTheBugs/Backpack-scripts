# public/get_market.py

import requests

def get_market(symbol):
    # retirer '_PERP' si présent
    if symbol.endswith('_PERP'):
        symbol = symbol.replace('_PERP', '')

    url = f"https://api.backpack.exchange/v1/market/{symbol}"
    response = requests.get(url)

    if response.status_code == 404:
        print(f"⚠️ Marché {symbol} non trouvé (404)")
        return None

    response.raise_for_status()
    return response.json()

market = get_market("BTC_USDC_PERP")
if market:
    print(f"Symbole: {market['symbol']}, Type: {market['marketType']}")