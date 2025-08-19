# utils/position_utils.py
import os
from datetime import datetime
from bpx.account import Account
from utils.logger import log
from config.settings import get_config

# Charger la configuration
config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

account = Account(public_key=public_key, secret_key=secret_key)


def get_real_positions():
    """
    Récupère les positions ouvertes réelles depuis Backpack Exchange
    et calcule le PnL réel.
    """
    positions = account.get_positions()  # Hypothétique fonction de l'API
    result = []

    for pos in positions:
        symbol = pos["symbol"]
        side = pos["side"]
        entry_price = pos["entry_price"]
        amount = pos["amount"]
        leverage = pos.get("leverage", 1)
        timestamp = pos.get("timestamp", datetime.utcnow())

        pnl_data = get_real_pnl(symbol, side, entry_price, amount, leverage)

        result.append({
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "amount": amount,
            "leverage": leverage,
            "timestamp": timestamp,
            "pnl_usd": pnl_data["pnl_usd"],
            "pnl_percent": pnl_data["pnl_percent"],
        })

    return result


def get_real_pnl(symbol: str, side: str, entry_price: float, amount: float, leverage: float = 1.0) -> dict:
    """
    Calcule le PnL réel en USD et en %.
    """
    # Import local pour éviter circular import
    from utils.get_market import get_market

    mark_price = get_market(symbol)["price"]
    if mark_price is None or mark_price == 0:
        mark_price = entry_price

    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
    else:
        pnl_usd = (entry_price - mark_price) * amount

    pnl_percent = (pnl_usd / (entry_price * amount)) * leverage * 100
    return {"pnl_usd": pnl_usd, "pnl_percent": pnl_percent}


def position_already_open(symbol: str):
    """
    Vérifie si une position est déjà ouverte pour le symbole.
    """
    positions = get_real_positions()
    for pos in positions:
        if pos["symbol"] == symbol:
            return True
    return False
