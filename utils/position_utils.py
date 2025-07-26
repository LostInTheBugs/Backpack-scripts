import os
import time
import hmac
import hashlib
import requests

API_URL = "https://api.backpack.exchange/api/v1/position"

public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

def generate_signature(secret_key: str, method: str, path: str, timestamp: str, body: str = "") -> str:
    """
    Génère la signature HMAC SHA256 requise par l'API Backpack.
    La chaîne signée est généralement : timestamp + méthode + chemin + body (body vide pour GET).
    """
    message = f"{timestamp}{method}{path}{body}"
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return signature

def position_already_open(symbol: str) -> bool:
    """
    Vérifie si une position ouverte existe pour le symbole donné.
    """
    method = "GET"
    path = "/api/v1/position"
    timestamp = str(int(time.time() * 1000))  # timestamp en millisecondes
    
    signature = generate_signature(secret_key, method, path, timestamp)

    headers = {
        "X-API-KEY": public_key,
        "X-Signature": signature,
        "X-Timestamp": timestamp
    }

    try:
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()
        data = response.json()
        # data est une liste de positions ouvertes, filtrer par symbole et taille non nulle
        for pos in data:
            if pos.get("symbol") == symbol and float(pos.get("size", 0)) != 0:
                return True
        return False
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error lors de la vérification des positions : {e}")
        return False
    except Exception as e:
        print(f"Erreur vérif position ouverte : {e}")
        return False
