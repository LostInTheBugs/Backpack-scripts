import os
import time
import pandas as pd
import requests
from ta.momentum import RSIIndicator
from private import Client  # Ton wrapper Backpack privé
from public import get_market

# Clés d'API depuis variables d'environnement
API_KEY = os.getenv("bpx_bot_public_key")
API_SECRET = os.getenv("bpx_bot_secret_key")
client = Client(api_key=API_KEY, api_secret=API_SECRET)

def get_ohlcv(symbol: str, interval="1m", limit=100):
    url = f"https://api.backpack.exchange/api/v1/ohlcv/{symbol}"
    params = {"resolution": interval, "limit": limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data)
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df["close"] = pd.to_numeric(df["close"])
    return df

def compute_rsi(df: pd.DataFrame, period=14):
    rsi = RSIIndicator(close=df["close"], window=period)
    return rsi.rsi().iloc[-1]

def trade_rsi(symbol: str, usdc_amount=10):
    market = get_market(symbol)
    base_token = market["baseToken"]
    quote_token = market["quoteToken"]

    df = get_ohlcv(symbol)
    rsi = compute_rsi(df)

    print(f"RSI pour {symbol}: {rsi:.2f}")

    if rsi < 30:
        print("RSI < 30 → Achat")
        client.market_order(symbol, side="buy", quote_amount=usdc_amount)

    elif rsi > 70:
        print("RSI > 70 → Vente")
        balance = client.get_token_balance(base_token)
        if balance > 0:
            client.market_order(symbol, side="sell", base_amount=balance)
        else:
            print("Pas de token à vendre.")
    else:
        print("RSI entre 30 et 70 → Neutre")

# Boucle principale
if __name__ == "__main__":

    while True:
        try:
            trade_rsi(symbol)
        except Exception as e:
            print(f"Erreur : {e}")
        time.sleep(60)
