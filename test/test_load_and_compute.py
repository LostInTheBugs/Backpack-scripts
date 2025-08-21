from indicators import combined_indicators as ci
from utils.logger import log
import pandas as pd

def test(symbol="BTC_USDC_PERP"):
    log(f"[{symbol}] Début test chargement + calcul indicateurs", level="INFO")

    # Charge les données OHLCV depuis la base (dernière heure par défaut)
    df = ci.load_ohlcv_from_db(symbol)
    if df is None or df.empty:
        log(f"[{symbol}] [ERROR] Pas de données chargées, test interrompu.", level="ERROR")
        return

    log(f"[{symbol}] Chargement des données OHLCV depuis la base...", level="INFO")

    # Calcule tous les indicateurs
    df_calc = ci.compute_all(df, symbol=symbol)

    # Affiche un aperçu des résultats
    pd.set_option('display.max_columns', None)
    print(f"\n[{symbol}] Données calculées, aperçu :\n", df_calc.tail(5))

if __name__ == "__main__":
    test()
