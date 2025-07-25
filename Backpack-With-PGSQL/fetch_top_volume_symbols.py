import requests
import json

# Paramètres
BASE_URL = "https://api.backpack.exchange/api/v1/tickers"
SYMBOLS_FILE = "symbol.lst"
TOP_N = 10  # Nombre de symboles à récupérer

def fetch_top_symbols(n=TOP_N):
    """Récupère les n symboles avec le plus grand volume sur 24h."""
    response = requests.get(BASE_URL)
    if response.status_code != 200:
        print(f"Erreur lors de la récupération des données : {response.status_code}")
        return []

    tickers = response.json()
    # Trie les tickers par volume décroissant
    sorted_tickers = sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
    top_symbols = [ticker['symbol'] for ticker in sorted_tickers[:n]]
    return top_symbols

def save_symbols(symbols):
    """Sauvegarde les symboles dans le fichier symbol.lst."""
    with open(SYMBOLS_FILE, 'w') as f:
        for symbol in symbols:
            f.write(f"{symbol}\n")
    print(f"✅ {len(symbols)} symboles sauvegardés dans {SYMBOLS_FILE}")

if __name__ == "__main__":
    top_symbols = fetch_top_symbols()
    if top_symbols:
        save_symbols(top_symbols)
