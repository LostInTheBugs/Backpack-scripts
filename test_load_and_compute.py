# test_load_and_compute.py
import os
from indicators.combined_indicators import load_ohlcv_from_db, compute_all
from utils.logger import log

def main():
    symbol = "BTC_USDC_PERP"
    log(f"Chargement des données pour {symbol} depuis PostgreSQL...", level="INFO")
    df = load_ohlcv_from_db(symbol, limit=500)
    if df is None:
        log(f"Aucune donnée disponible pour {symbol}, arrêt.", level="ERROR")
        return

    log(f"Données chargées : {len(df)} lignes", level="INFO")
    log(f"Aperçu des données:\n{df.head()}", level="INFO")

    df_ind = compute_all(df, symbol=symbol)

    log(f"Indicateurs calculés, aperçu des colonnes:\n{df_ind.columns}", level="INFO")
    log(f"Aperçu des indicateurs calculés:\n{df_ind.tail()}", level="INFO")

if __name__ == "__main__":
    main()
