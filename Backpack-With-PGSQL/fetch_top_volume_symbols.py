import requests
import sys

API_URL = "https://api.backpack.exchange/v1/tickers"
OUTPUT_FILE = "symbol.lst"

def fetch_top_n_perp(n):
    resp = requests.get(API_URL)
    resp.raise_for_status()
    data = resp.json()

    # data attendue : liste de dict, chaque dict a 'symbol' et 'quoteVolume' (string)
    perp_tickers = [t for t in data if "_PERP" in t.get("symbol", "")]

    # tri par quoteVolume float décroissant
    perp_tickers.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)

    top_n = perp_tickers[:n]

    with open(OUTPUT_FILE, "w") as f:
        for t in top_n:
            f.write(t["symbol"] + "\n")

    print(f"✅ Écrit {len(top_n)} symboles PERP dans {OUTPUT_FILE}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} N")
        sys.exit(1)
    try:
        n = int(sys.argv[1])
    except ValueError:
        print("N doit être un entier")
        sys.exit(1)

    fetch_top_n_perp(n)
