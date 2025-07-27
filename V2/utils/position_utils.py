import os
import aiohttp
from bpx.account import Account

public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

# Initialisation de l'objet Account (gère signature, nonce, etc.)
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)

def position_already_open(symbol: str) -> bool:
    """
    Vérifie si une position ouverte existe pour le symbole donné.
    Retourne True si une position non nulle est ouverte, sinon False.
    """
    try:
        positions = account.get_open_positions()
        for p in positions:
            if p.get("symbol") == symbol and float(p.get("netQuantity", 0)) != 0:
                return True
        return False
    except Exception as e:
        print(f"Erreur vérif position ouverte : {e}")
        return False

async def get_open_positions():
    method = "GET"
    path = "/api/v1/trade/positions"
    body = {}  # vide pour GET

    try:
        response = await account.signed_request(
            method=method,
            path=path,
            body=body
        )

        data = response.get("positions", [])

        positions = {}
        for p in data:
            if float(p["size"]) != 0:
                symbol = p["symbol"]
                side = "long" if float(p["size"]) > 0 else "short"
                entry_price = float(p["entryPrice"])
                positions[symbol] = {
                    "side": side,
                    "entry_price": entry_price
                }

        return positions

    except Exception as e:
        print(f"❌ Erreur API signée Backpack : {e}")
        return {}