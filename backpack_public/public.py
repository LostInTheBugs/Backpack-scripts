import pandas as pd
import requests

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 100):
    """
    Récupère les données OHLCV depuis l'API officielle de Backpack Exchange
    et retourne un DataFrame avec les colonnes correctement typées.
    """
    url = f"https://api.backpack.exchange/api/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Conversion des colonnes numériques
        for col in ['open', 'high', 'low', 'close', 'volume', 'quoteVolume', 'trades']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Conversion des dates
        if 'start' in df.columns:
            df['start'] = pd.to_datetime(df['start'])
        if 'end' in df.columns:
            df['end'] = pd.to_datetime(df['end'])

        return df

    except Exception as e:
        print(f"[get_ohlcv] ❌ Erreur lors de la récupération OHLCV : {e}")
        return pd.DataFrame()
