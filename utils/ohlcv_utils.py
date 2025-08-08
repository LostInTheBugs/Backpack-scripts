import pandas as pd
from utils.public import get_ohlcv

def get_ohlcv_df(symbol: str, interval: str = "1m", limit: int = 21):
    """
    Appelle get_ohlcv() et retourne un DataFrame pandas proprement converti.
    """
    data = get_ohlcv(symbol, interval=interval, limit=limit)

    if not isinstance(data, list) or len(data) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(data)

    # Convertir les colonnes numériques
    for col in ['open', 'high', 'low', 'close', 'volume', 'quoteVolume', 'trades']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Convertir les timestamps si présents
    if 'start' in df.columns:
        df['start'] = pd.to_datetime(df['start'])
    if 'end' in df.columns:
        df['end'] = pd.to_datetime(df['end'])

    return df
