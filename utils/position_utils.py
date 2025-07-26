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

    try:
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()
        data = response.json()
        # data est probablement une liste d'objets position
        for pos in data:
            # vérifier que la clé 'symbol' et 'size' existent dans pos
            if pos.get("symbol") == symbol and float(pos.get("size", 0)) != 0:
                return True
        return False
    except requests.HTTPError as http_err:
        print(f"HTTP error lors de la vérification des positions : {http_err}")
    except Exception as e:
        print(f"Erreur vérif position ouverte : {e}")
    return False
