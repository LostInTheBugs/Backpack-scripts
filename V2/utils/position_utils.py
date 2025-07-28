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
            if float(p.get("netQuantity", 0)) != 0:
                symbol = p["symbol"]
                entry_price = float(p["entryPrice"])
                side = "long" if float(p["netQuantity"]) > 0 else "short"

                positions[symbol] = {
                    "entry_price": entry_price,
                    "side": side
                }
        return positions

    except Exception as e:
        print(f"⚠️ Erreur get_open_positions(): {e}")
        return {}

def get_real_pnl(symbol: str) -> float:
    try:
        positions = account.get_open_positions()
        for p in positions:
            if p.get("symbol") == symbol and float(p.get("netQuantity", 0)) != 0:
                pnl = float(p.get("unrealizedPnl", 0))
                print(f"DEBUG get_real_pnl: symbol={symbol}, unrealizedPnl={pnl}")
                entry_price = float(p.get("entryPrice", 0))
                quantity = float(p.get("netQuantity", 0))
                print(f"DEBUG get_real_pnl: symbol={symbol}, unrealizedPnl={pnl}, entryPrice={entry_price}, netQuantity={quantity}")
                return pnl
        print(f"DEBUG get_real_pnl: symbol={symbol} pas de position ouverte")
        return 0.0
    except Exception as e:
        print(f"Erreur get_real_pnl(): {e}")
        return 0.0