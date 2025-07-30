import requests
import sys

API_URL = "https://api.backpack.exchange/api/v1/tickers"
OUTPUT_FILE = "symbol.lst"

def fetch_top_n_volatility_volume(n):
    try:
        resp = requests.get(API_URL)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des données : {e}")
        sys.exit(1)

    data = resp.json()
    perp_tickers = [t for t in data if "_PERP" in t.get("symbol", "")]

    tickers_data = []
    for t in perp_tickers:
        try:
            symbol = t["symbol"]
            price_change_percent = abs(float(t.get("priceChangePercent", 0)))
            volume = float(t.get("volume", 0))  # Volume 24h
            tickers_data.append((symbol, price_change_percent, volume))
        except Exception:
            continue

    # 💡 Filtrer ceux avec volume < 1 million
    tickers_data = [
        (symbol, price_change_percent, volume)
        for symbol, price_change_percent, volume in tickers_data
        if volume >= 1_000_000
    ]

    if not tickers_data:
        print("❌ Aucun ticker avec un volume >= 1 million")
        sys.exit(1)

    max_volume = max(t[2] for t in tickers_data)

    scored_tickers = []
    for symbol, volat, vol in tickers_data:
        volume_norm = vol / max_volume if max_volume > 0 else 0
        score = volat * volume_norm
        scored_tickers.append((symbol, score))

    scored_tickers.sort(key=lambda x: x[1], reverse=True)
    top_n = scored_tickers[:n]

    with open(OUTPUT_FILE, "w") as f:
        for symbol, score in top_n:
            f.write(symbol + "\n")

    print(f"✅ Écrit {len(top_n)} symboles les plus volatils (volume ≥ 1M) dans {OUTPUT_FILE}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} N")
        sys.exit(1)

    try:
        n = int(sys.argv[1])
    except ValueError:
        print("N doit être un entier")
        sys.exit(1)

    fetch_top_n_volatility_volume(n)
