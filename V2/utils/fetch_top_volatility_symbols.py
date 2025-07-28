import requests
import sys

API_URL = "https://api.backpack.exchange/api/v1/tickers"
OUTPUT_FILE = "symbol.lst"

def fetch_top_n_volatility(n):
    try:
        resp = requests.get(API_URL)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erreur lors de la récupération des données : {e}")
        sys.exit(1)

    data = resp.json()
    perp_tickers = [t for t in data if "_PERP" in t.get("symbol", "")]

    # Calcul de la volatilité journalière : (high - low) / open
    tickers_with_volatility = []
    for t in perp_tickers:
        try:
            high = float(t.get("high", 0))
            low = float(t.get("low", 0))
            open_price = float(t.get("open", 0))
            if open_price > 0:
                volatility = (high - low) / open_price * 100
                tickers_with_volatility.append((t["symbol"], volatility))
        except Exception:
            continue  # Ignore les symboles avec des données manquantes ou invalides

    # Tri par volatilité décroissante
    tickers_with_volatility.sort(key=lambda x: x[1], reverse=True)

    top_n = tickers_with_volatility[:n]

    with open(OUTPUT_FILE, "w") as f:
        for symbol, vol in top_n:
            f.write(symbol + "\n")

    print(f"✅ Écrit {len(top_n)} symboles les plus volatils dans {OUTPUT_FILE}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} N")
        sys.exit(1)

    try:
        n = int(sys.argv[1])
    except ValueError:
        print("N doit être un entier")
        sys.exit(1)

    fetch_top_n_volatility(n)
