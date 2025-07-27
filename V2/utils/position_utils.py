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
    url = "https://api.backpack.exchange/api/v1/trade/positions"
    method = "GET"
    path = "/api/v1/trade/positions"
    body = ""  # vide pour GET sans query
    query = ""

    # Signature
    headers = account.sign(method, path, body, query)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise Exception(f"Erreur API position: {response.status} {await response.text()}")

            data = await response.json()

            positions = {}
            for p in data.get("positions", []):
                if float(p["size"]) != 0:
                    symbol = p["symbol"]
                    side = "long" if float(p["size"]) > 0 else "short"
                    entry_price = float(p["entryPrice"])
                    positions[symbol] = {
                        "side": side,
                        "entry_price": entry_price
                    }
            return positions