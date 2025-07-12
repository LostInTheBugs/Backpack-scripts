import os
import sys
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from bpx.public import Public
from bpx.private import Client

# === Clés API depuis variables d'environnement ===
API_KEY = os.getenv("bpx_bot_public_key")
API_SECRET = os.getenv("bpx_bot_secret_key")

if not API_KEY or not API_SECRET:
    print("❌ Clés API manquantes. Vérifie tes variables d'environnement.")
    sys.exit(1)

# === Initialisation des clients API ===
public_api = Public()
client = Client(api_key=API_KEY, api_secret=API_SECRET)

# === Fonction de récupération des données OHLCV ===
def get_ohlcv(symbol: str, interval="1m", limit=100):
    url = f"https://api.backpack.exchange/api/v1/ohlcv/{symbol}"
    params = {"resolution": interval, "limit": limit}
    resp = requests.get(url, params=params)
    if not resp.ok:
        raise Exception(f"Erreur API OHLCV : {resp.text}")
    df = pd.DataFrame(resp.json())
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df["close"] = pd.to_numeric(df["close"])
    return df

# === Calcul RSI ===
def compute_rsi(df: pd.DataFrame, period=14):
    rsi = RSIIndicator(close=df["close"], window=period)
    return rsi.rsi().iloc[-1]

# === Analyse RSI ===
def analyse_rsi(symbol: str):
    print(f"🔍 Analyse RSI pour {symbol}")
    df = get_ohlcv(symbol)
    rsi = compute_rsi(df)
    print(f"RSI actuel : {rsi:.2f}")

    if rsi < 30:
        print("🟢 RSI < 30 : Signal d'ACHAT")
    elif rsi > 70:
        print("🔴 RSI > 70 : Signal de VENTE")
    else:
        print("⚪ RSI neutre (entre 30 et 70) : PAS D'ACTION")

# === Lancement ===
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Utilisation : python rsi_signal.py SYMBOL")
        print("Exemple : python rsi_signal.py SOL_USDC")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        analyse_rsi(symbol)
    except Exception as e:
        print(f"❌ Erreur : {e}")
