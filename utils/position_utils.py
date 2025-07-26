import os
import requests

API_URL = "https://api.backpack.exchange/api/v1/position"

public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

def position_already_open(symbol: str) -> bool:
    headers = {
        "X-API-KEY": public_key,
        "X-API-SECRET": secret_key
    }

    url = f"{API_URL}?symbol={symbol}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        for pos in data:
            if pos.get("symbol") == symbol and float(pos.get("size", 0)) != 0:
                return True
        return False
    except requests.HTTPError as http_err:
        print(f"HTTP error lors de la vérification des positions : {http_err}")
    except Exception as e:
        print(f"Erreur vérif position ouverte : {e}")
    return False