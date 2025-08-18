import os
import asyncio
from bpx.account import Account
from utils.logger import log

public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

# Objet Account central
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)


async def position_already_open(symbol: str) -> bool:
    """
    Vérifie si une position ouverte existe pour le symbole donné.
    Retourne True si une position non nulle est ouverte, sinon False.
    """
    try:
        positions = await asyncio.to_thread(account.get_open_positions)
        for p in positions:
            if p.get("symbol") == symbol and float(p.get("netQuantity", 0)) != 0:
                return True
        return False
    except Exception as e:
        log(f"Erreur vérif position ouverte : {e}", level="error")
        return False


async def get_open_positions():
    """
    Récupère toutes les positions ouvertes sous forme de dict:
    { symbol: {entry_price, side} }
    """
    try:
        raw_positions = await asyncio.to_thread(account.get_open_positions)
        positions = {}
        for p in raw_positions:
            net_qty = float(p.get("netQuantity", 0))
            if net_qty != 0:
                symbol = p["symbol"]
                entry_price = float(p.get("entryPrice", 0))
                side = "long" if net_qty > 0 else "short"
                positions[symbol] = {
                    "entry_price": entry_price,
                    "side": side,
                    "net_qty": net_qty
                }
        return positions
    except Exception as e:
        log(f"⚠️ Erreur get_open_positions(): {e}", level="error")
        return {}


async def get_real_pnl(symbol: str):
    """
    Retourne le PnL non réalisé et la valeur notionnelle pour le symbole donné.
    """
    try:
        positions = await asyncio.to_thread(account.get_open_positions)
        for position in positions:
            if position["symbol"] == symbol and float(position.get("netQuantity", 0)) != 0:
                pnl_unrealized = float(position.get("pnlUnrealized", 0))
                notional = float(position.get("netExposureNotional", 1))  # fallback à 1 pour éviter div0
                return pnl_unrealized, notional
        return 0.0, 1.0
    except Exception as e:
        log(f"⚠️ Erreur get_real_pnl({symbol}): {e}", level="error")
        return 0.0, 1.0


from utils.get_market import get_market  
