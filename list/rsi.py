import os
import time
import hmac
import base64
import hashlib
import requests
import pandas as pd
from ta.momentum import RSIIndicator
import json
import sys

# === Client minimal Backpack Exchange ===
class Client:
    def __init__(self, api_key, api_secret):
        self.base_url = "https://api.backpack.exchange/api/v1"
        self.api_key = api_key
        self.api_secret = api_secret

    def _headers(self, method, path, body=""):
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{method.upper()}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.b64encode(signature).decode()

        return {
            "BP-API-KEY": self.api_key,
            "BP-API-SIGN": signature_b64,
            "BP-API-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    def get_token_balance(self, symbol="USDC"):
        path = "/wallet/balances"
        url = self.base_url + path
        headers = self._headers("GET", path)
        resp = requests.get(url, headers=headers)
        balances = resp.json()
        for b in balances:
            if b["token"]["symbol"] == symbol:
                return float(b["available"])
        return 0.0

    def market_order(self, symbol, side, quote_amount=None, base_amount=None):
        path = "/order"
        url = self.base_url + path

        market_data = {
            "symbol": symbol,
            "side": side,
            "type": "market",
        }

        if quote_amount:
            market_data["quoteAmount"] = str(quote_amount)
        elif base_amount:
            market_data["baseAmount"] = str(base_amount)
        else:
            raise ValueError("quote_amount ou base_amount requis")

        body = json.dumps(market_data)
        headers = self._headers("POST", path, body)
        resp = requests.post(url, headers=headers, data=body)

        if resp.ok:
            return resp.json()
        else:
            raise Exception(f"Erreur ordre : {resp.status_code} {resp.text}")

# === Fonctions techniques ===

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

def compute_rsi(df: pd.DataFrame, period=14):
    rsi = RSIIndicator(close=df["close"], window=period)
    return rsi.rsi().iloc[-1]

# === Action RSI ===

def trade_rsi(symbol: str, client: Client, quote_token="USDC", base_token=None, usdc_amount=1):
    df = get_ohlcv(symbol)
    rsi = compute_rsi(df)

    print(f"📊 RSI actuel pour {symbol} : {rsi:.2f}")

    if rsi < 30:
        print("🟢 RSI < 30 → Signal d'ACHAT")
        balance = client.get_token_balance(quote_token)
        print(f"💰 Solde {quote_token} : {balance}")
        if balance >= usdc_amount:
            res = client.market_order(symbol, side="buy", quote_amount=usdc_amount)
            print("✅ Ordre d'achat exécuté :", res)
        else:
            print("❌ Solde insuffisant pour acheter.")
    elif rsi > 70:
        print("🔴 RSI > 70 → Signal de VENTE")
        if not base_token:
            base_token = symbol.split("_")[0]
        balance = client.get_token_balance(base_token)
        print(f"💰 Solde {base_token} : {balance}")
        if balance > 0:
            res = client.market_order(symbol, side="sell", base_amount=balance)
            print("✅ Ordre de vente exécuté :", res)
        else:
            print("❌ Aucun token à vendre.")
    else:
        print("⚪ RSI neutre → Pas d'action.")

# === Lancement ===

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Utilisation : python rsi_trader.py SYMBOL")
        print("Exemple : python rsi_trader.py SOL_USDC")
        sys.exit(1)

    symbol = sys.argv[1]
    base_token = symbol.split("_")[0]
    quote_token = symbol.split("_")[1]

    # Récupération des clés API
    key = os.getenv("bpx_bot_public_key")
    secret = os.getenv("bpx_bot_secret_key")

    if not key or not secret:
        print("❌ Clés API manquantes.")
        sys.exit(1)

    client = Client(api_key=key, api_secret=secret)

    # Lancer une seule fois
    try:
        trade_rsi(symbol, client, quote_token=quote_token, base_token=base_token, usdc_amount=1)
    except Exception as e:
        print(f"💥 Erreur : {e}")
