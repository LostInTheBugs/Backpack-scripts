import requests
import sys
from utils.logger import log

API_URL = "https://api.backpack.exchange/api/v1/tickers"
OUTPUT_FILE = "symbol.lst"

def fetch_top_n_volatility_volume(n=None):
    try:
        resp = requests.get(API_URL)
        resp.raise_for_status()
    except Exception as e:
        log(f"[ERROR] ❌ Erreur lors de la récupération des données : {e}", level="ERROR")
        return []

    data = resp.json()
    perp_tickers = [t for t in data if "_PERP" in t.get("symbol", "")]

    tickers_data = []
    for t in perp_tickers:
        try:
            symbol = t["symbol"]
            price_change_percent = abs(float(t.get("priceChangePercent", 0)))
            volume = float(t.get("volume", 0))
            tickers_data.append((symbol, price_change_percent, volume))
        except Exception:
            continue

    tickers_data = [
        (symbol, price_change_percent, volume)
        for symbol, price_change_percent, volume in tickers_data
        if volume >= 1_000_000
    ]

    if not tickers_data:
        log("[ERROR] ❌ Aucun ticker avec un volume >= 1 million", level="ERROR")
        return []

    max_volume = max(t[2] for t in tickers_data)

    scored_tickers = []
    for symbol, volat, vol in tickers_data:
        volume_norm = vol / max_volume if max_volume > 0 else 0
        score = volat * volume_norm
        scored_tickers.append((symbol, score))

    scored_tickers.sort(key=lambda x: x[1], reverse=True)

    if n is None:
        top_n = scored_tickers
    else:
        top_n = scored_tickers[:n]

    symbols_list = [symbol for symbol, score in top_n]

    log(f"[DEBUG] ✅ {len(symbols_list)} symboles les plus volatils (volume ≥ 1M) récupérés.", level="DEBUG")
    return symbols_list

if __name__ == "__main__":
    # Parse argument avec --no-limit support
    if len(sys.argv) == 2:
        arg = sys.argv[1]
        if arg == "--no-limit":
            n = None
        else:
            try:
                n = int(arg)
            except ValueError:
                print("N doit être un entier ou --no-limit")
                sys.exit(1)
    else:
        print(f"Usage: python3 {sys.argv[0]} N | --no-limit")
        sys.exit(1)

    fetch_top_n_volatility_volume(n)
