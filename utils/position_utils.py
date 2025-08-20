# utils/position_utils.py
import os
import asyncio
from bpx.account import Account
from utils.logger import log
from config.settings import get_config
from typing import List, Dict, Any

# Charger la configuration
config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

log(f"Using public_key={public_key}, secret_key={'***' if secret_key else None}", level="DEBUG")

# Création de l'objet Account central
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def safe_float(val, default=0.0):
    """Convertit val en float, même si c'est une string invalide ou vide."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def parse_position(raw_pos: dict) -> dict:
    """
    Transforme une position brute de Backpack en dict normalisé avec floats.
    """
    try:
        entry_price = safe_float(raw_pos.get("entryPrice"), 0.0)
        mark_price = safe_float(raw_pos.get("markPrice"), entry_price)
        net_qty = safe_float(raw_pos.get("netQuantity"), 0.0)
        pnl_unrealized = safe_float(raw_pos.get("pnlUnrealized"), 0.0)

        if net_qty == 0:
            return {}

        # Déterminer le sens de la position
        side = "long" if net_qty > 0 else "short"

        # Calcul du PnL % en fonction du side
        pnl_pct = 0.0
        if entry_price > 0:
            if side == "long":
                pnl_pct = (mark_price - entry_price) / entry_price * 100
            else:  # short
                pnl_pct = (entry_price - mark_price) / entry_price * 100

        return {
            "symbol": raw_pos.get("symbol"),
            "entry_price": entry_price,
            "mark_price": mark_price,
            "side": side,
            "amount": abs(net_qty),
            "pnl_usd": pnl_unrealized,
            "pnl_pct": pnl_pct
        }

    except Exception as e:
        log(f"[ERROR] parse_position failed for {raw_pos}: {e}", level="ERROR")
        return {}


# ------------------------------------------------------------
# Fonctions principales
# ------------------------------------------------------------
async def get_raw_positions():
    """Récupère toutes les positions depuis l'API Backpack (asynchrone)."""
    try:
        positions = account.get_open_positions()
        return positions or []
    except Exception as e:
        log(f"[ERROR] Failed to fetch positions: {e}", level="ERROR")
        return []


async def get_open_positions() -> Dict[str, dict]:
    """
    Retourne un dict {symbol: {...}} pour les positions ouvertes.
    """
    positions = await get_raw_positions()
    result = {}

    for p in positions:
        parsed = parse_position(p)
        if parsed:
            result[parsed["symbol"]] = parsed

    return result


async def position_already_open(symbol: str) -> bool:
    """
    Vérifie si une position est déjà ouverte pour le symbole.
    """
    positions = await get_real_positions()
    return any(pos["symbol"] == symbol for pos in positions)


async def get_real_pnl(symbol, side, entry_price, amount, leverage):
    """
    Calcule le PnL réel d'une position.
    Retourne toujours un dict homogène.
    """
    from utils.get_market import get_market

    market = await get_market(symbol)
    if not market:
        log(f"[WARN] Market data not found for {symbol}, using entry_price as mark_price")
        mark_price = entry_price
    else:
        mark_price = safe_float(market.get("price"), entry_price)

    # ✅ PnL USD
    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
    else:  # short
        pnl_usd = (entry_price - mark_price) * amount

    # ✅ PnL %
    pnl_percent = 0.0
    if entry_price > 0:
        if side.lower() == "long":
            pnl_percent = (mark_price - entry_price) / entry_price * 100 * leverage
        else:
            pnl_percent = (entry_price - mark_price) / entry_price * 100 * leverage

    return {
        "pnl": pnl_usd,             # alias pour compatibilité
        "pnl_usd": pnl_usd,
        "pnl_percent": pnl_percent,
        "mark_price": mark_price
    }


async def get_real_positions() -> List[dict]:
    """
    Récupère les positions ouvertes réelles depuis Backpack Exchange
    et les retourne sous forme de liste de dictionnaires.
    """
    try:
        raw_positions = account.get_open_positions()
    except Exception as e:
        log(f"[ERROR] Cannot fetch positions: {e}", level="ERROR")
        return []

    positions_list = []

    for pos in raw_positions:
        parsed = parse_position(pos)
        if parsed:
            positions_list.append(parsed)

    return positions_list