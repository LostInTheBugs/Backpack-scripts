from datetime import datetime, timezone
from indicators import combined_indicators as ci
from utils.logger import log

def main():
    symbol = "BTC_USDC_PERP"
    log(f"[{symbol}] Début test chargement + calcul indicateurs", level="INFO")

    try:
        df = ci.compute_all(df=None, symbol=symbol)
        log(f"[{symbol}] Données calculées, aperçu :\n{df.tail(5)}", level="INFO")
    except Exception as e:
        log(f"[{symbol}] Erreur lors du test : {e}", level="ERROR")

if __name__ == "__main__":
    main()
