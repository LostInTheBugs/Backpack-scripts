import pandas as pd
import requests  # ou l'import utilisé pour appeler l'API

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 100):
    """
    Récupère les données OHLCV de Backpack Exchange et retourne un DataFrame prêt à l'emploi.
    """
    # --- 1. Récupération des données depuis l'API ---
    url = f"https://api.backpack.exchange/api/v1/ohlcv?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()  # la structure est probablement une liste de dicts

    if not isinstance(data, list) or len(data) == 0:
        return pd.DataFrame()

    # --- 2. Conversion en DataFrame ---
    df = pd.DataFrame(data)

    # --- 3. Conversion des colonnes numériques ---
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quoteVolume', 'trades']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- 4. Conversion des dates ---
    if 'start' in df.columns:
        df['start'] = pd.to_datetime(df['start'])
    if 'end' in df.columns:
        df['end'] = pd.to_datetime(df['end'])

    return df
