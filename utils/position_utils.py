import requests
import os
import time
import hmac
import hashlib

def position_already_open(symbol):
    api_key = os.getenv("bpx_bot_public_key")
    api_secret = os.getenv("bpx_bot_secret_key")

    url_path = "/api/v1/positions"
    url = f"https://api.backpack.exchange{url_path}"
    method = "GET"
    nonce = str(int(time.time() * 1000))
    body = ""

    prehash_string = f"{nonce}{method}{url_path}{body}"
    signature = hmac.new(
        api_secret.encode(), prehash_string.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "X-API-KEY": api_key,
        "X-API-NONCE": nonce,
        "X-API-SIGNATURE": signature,
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    positions = response.json()

    for pos in positions:
        if pos["symbol"] == symbol:
            size = float(pos.get("size", 0))
            return abs(size) > 0

    return False
