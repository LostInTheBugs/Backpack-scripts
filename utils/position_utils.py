import os
import time
import hmac
import hashlib
import requests

API_BASE = "https://api.backpack.exchange"
ENDPOINT = "/api/v1/position"
URL = API_BASE + ENDPOINT

public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

def sign_request(secret, nonce, method, path, body=""):
    message = f"{nonce}{method}{path}{body}"
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return signature

def position_already_open(symbol: str) -> bool:
    nonce = str(int(time.time() * 1000))
    method = "GET"
    path = ENDPOINT
    body = ""

    print(f"DEBUG nonce: {nonce}")
    print(f"DEBUG method: {method}")
    print(f"DEBUG path: {path}")
    print(f"DEBUG body: '{body}'")

    signature = sign_request(secret_key, nonce, method, path, body)

    headers = {
        "X-API-KEY": public_key,
        "X-API-NONCE": nonce,
        "X-API-SIGNATURE": signature
    }

    print("DEBUG headers:", headers)

    try:
        response = requests.get(URL, headers=headers)
        print("DEBUG status code:", response.status_code)
        response.raise_for_status()
        data = response.json()
        print("DEBUG data:", data)

        for pos in data:
            if pos["symbol"] == symbol and float(pos.get("size", 0)) != 0:
                return True
        return False

    except Exception as e:
        print(f"❌ Erreur vérif position ouverte : {e}")
        return False
