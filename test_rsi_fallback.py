from combined_indicators import compute_all
from utils.logger import log

if __name__ == "__main__":
    try:
        df = compute_all(symbol="BTC_USDC_PERP")
        log(f"DataFrame calculé avec {len(df)} lignes")
        log(df.tail())
    except Exception as e:
        log(f"Erreur dans le calcul des indicateurs: {e}")
