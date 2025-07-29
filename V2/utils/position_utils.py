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
    try:
        raw_positions = account.get_open_positions()
        positions = {}
        for p in raw_positions:
            if float(p.get("q", 0)) != 0:
                symbol = p["s"]
                entry_price = float(p.get("B", 0))
                side = "long" if float(p.get("q")) > 0 else "short"
                positions[symbol] = {
                    "entry_price": entry_price,
                    "side": side
                }
        return positions
    except Exception as e:
        print(f"⚠️ Erreur get_open_positions(): {e}")
        return {}

from utils.get_market import get_market  # tu dois avoir une fonction async pour ça

def get_real_pnl(symbol: str):
    account = Account(public_key=public_key, secret_key=secret_key)
    positions = account.get_open_positions()

    for position in positions:
        if position["symbol"] == symbol and float(position.get("netQuantity", 0)) != 0:
            pnl_unrealized = float(position.get("pnlUnrealized", 0))
            notional = float(position.get("netExposureNotional", 1))  # <--- clé importante ici
            return pnl_unrealized, notional

    return 0.0, 1.0  # fallback pour éviter division par zéro