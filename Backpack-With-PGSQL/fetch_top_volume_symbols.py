import requests

SYMBOLS_FILE = "symbol.lst"
N = 10  # nombre de symboles à garder dans le fichier

def fetch_top_symbols(n):
    url = "https://api.backpack.exchange/api/v1/tickers"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Erreur récupération données API : {e}")
        return []

    # data attendue : liste d'objets avec 'symbol' et 'volume_24h' (ou similaire)
    # Adapter selon la vraie réponse API Backpack
    # Exemple d'objet : {'symbol': 'BTC_USDC_PERP', 'volume_24h': 123456.78, ...}

    # Filtrer uniquement les symboles perpétuels (si besoin)
    filtered = [item for item in data if item.get('symbol', '').endswith('_PERP')]

    # Trier par volume 24h décroissant
    sorted_syms = sorted(filtered, key=lambda x: float(x.get('volume_24h', 0)), reverse=True)

    top_symbols = [item['symbol'] for item in sorted_syms[:n]]
    return top_symbols

def save_symbols(symbols):
    with open(SYMBOLS_FILE, 'w') as f:
        for sym in symbols:
            f.write(sym + "\n")
    print(f"✅ {len(symbols)} symboles écrits dans {SYMBOLS_FILE}")

if __name__ == "__main__":
    top_syms = fetch_top_symbols(N)
    if top_syms:
        save_symbols(top_syms)
    else:
        print("⚠️ Pas de symboles récupérés")
