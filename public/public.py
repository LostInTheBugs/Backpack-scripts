import requests
import time

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 100):
    """
    Récupère les bougies OHLCV pour un symbole donné depuis l'API publique de Backpack Exchange.

    :param symbol: Exemple : 'BTC-USDC'
    :param interval: Intervalle des bougies : '1m', '5m', '15m', etc.
    :param limit: Nombre de bougies à récupérer
    :return: Liste de dictionnaires OHLCV
    """
    base_url = "https://api.backpack.exchange/api/v1"
    endpoint = f"/candles?symbol={symbol}&interval={interval}&limit={limit}"
    url = base_url + endpoint

    try:
        response = requests.get(url)
        response.raise_for_status()
        candles = response.json()

        return [
            {
                "timestamp": int(candle["startTime"]),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": float(candle["volume"]),
            }
            for candle in candles
        ]

    except Exception as e:
        print(f"❌ Erreur lors de la récupération des bougies : {e}")
        return []
