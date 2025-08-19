# utils/position_utils.py
import os
import asyncio
from datetime import datetime
from bpx.account import Account
from utils.logger import log
from config.settings import get_config
from utils.get_market import get_market

# Charger la configuration
config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

# Compte API
account = Account(public_key, secret_key)

# Cache PnL pour éviter les valeurs manquantes
pnl_cache = {}

def get_real_pnl(symbol: str, side: str, entry_price: float, amount: float, leverage: float = 1.0) -> dict:
    """
    Calcul du PnL réel pour une position.
    Retourne dict {pnl_usd, pnl_percent}.
    """
    market_data = get_market(symbol)
    mark_price = market_data.get("price") if market_data else entry_price

    if mark_price is None or mark_price == 0:
        mark_price = entry_price  # fallback

    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
    else:  # short
        pnl_usd = (entry_price - mark_price) * amount

    pnl_percent = (pnl_usd / (entry_price * amount)) * leverage * 100 if entry_price * amount != 0 else 0.0

    # Mettre à jour le cache
    pnl_cache[symbol] = {"pnl_usd": pnl_usd, "pnl_percent": pnl_percent, "timestamp": datetime.utcnow()}

    return {"pnl_usd": pnl_usd, "pnl_percent": pnl_percent}


def get_real_positions() -> list:
    """
    Récupère toutes les positions ouvertes avec PnL et infos utiles.
    Retourne une liste de dict :
    [
        {
            "symbol": "BTC_USDC",
            "side": "long",
            "entry_price": 30000,
            "amount": 0.01,
            "leverage": 1,
            "pnl_usd": 10.0,
            "pnl_percent": 0.33,
            "timestamp": datetime
        },
        ...
    ]
    """
    positions = []
    try:
        raw_positions = account.get_open_positions()  # Liste des positions depuis Backpack API
        for pos in raw_positions:
            symbol = pos["symbol"]
            side = pos["side"]
            entry_price = float(pos["entryPrice"])
            amount = float(pos["netQty"])
            leverage = float(pos.get("leverage", 1))

            pnl = get_real_pnl(symbol, side, entry_price, amount, leverage)

            positions.append({
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "amount": amount,
                "leverage": leverage,
                "pnl_usd": pnl["pnl_usd"],
                "pnl_percent": pnl["pnl_percent"],
                "timestamp": datetime.utcnow()
            })
    except Exception as e:
        log(f"[ERROR] get_real_positions: {e}")
    return positions


def position_already_open(symbol: str) -> bool:
    """
    Vérifie si une position est déjà ouverte pour un symbole.
    """
    positions = get_real_positions()
    return any(pos["symbol"] == symbol for pos in positions)


def get_open_positions() -> list:
    """
    Retourne la liste des symboles avec positions ouvertes.
    """
    positions = get_real_positions()
    return [pos["symbol"] for pos in positions]
