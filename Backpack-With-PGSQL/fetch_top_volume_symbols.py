import requests
import sys

API_URL = "https://api.backpack.exchange/api/v1/tickers"
OUTPUT_FILE = "symbol.lst"

def main(n):
    try:
        n = int(n)
        if n <= 0:
            raise ValueError()
    except:
        print("Usage: python3 update_symbols_by_volume.py N")
        print("N = nombre de symboles à garder selon volume 24h")
        sys.exit(1)

    resp = requests.get(API_URL)
    if resp.status_code != 200:
        print(f"Erreur HTTP {resp.status_code}")
        sys.exit(1)

    data = resp.json()
    # data est une liste d'objets, ex: {"symbol":"BTC_USDC_PERP", "volume": "12345.67", ...}

    # Convertir volume en float, trier par volume décroissant
    sorted_tickers = sorted(
        data,
        key=lambda x: float(x.get("volume", "0")),
        reverse=True
    )

    top_symbols = [t["symbol"] for t in sorted_tickers[:n]]

    with open(OUTPUT_FILE, "w") as f:
        for sym in top_symbols:
            f.write(sym + "\n")

    print(f"✅ Mis à jour {OUTPUT_FILE} avec les {n} symboles les plus volumineux :")
    print("\n".join(top_symbols))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 update_symbols_by_volume.py N")
        sys.exit(1)
    main(sys.argv[1])
