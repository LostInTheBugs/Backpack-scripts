# utils/position_utils.py
import os
import asyncio
from bpx.account import Account
from utils.logger import log
from config.settings import get_config
from typing import List, Dict, Any
from datetime import datetime

# Charger la configuration
config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

log(f"Using public_key={public_key}, secret_key={'***' if secret_key else None}", level="DEBUG")

# Création de l'objet Account central
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)


async def get_raw_positions():
    """Récupère toutes les positions depuis l'API Backpack (asynchrone)."""
    try:
        positions = account.get_open_positions()
        return positions or []
    except Exception as e:
        log(f"[ERROR] Failed to fetch positions: {e}", level="ERROR")
        return []


async def get_open_positions():
    """Retourne un dict {symbol: {entry_price, side, net_qty}} pour les positions ouvertes."""
    positions = await get_raw_positions()
    result = {}
    for p in positions:
        net_qty = safe_float(p.get("netQuantity"), 0.0)
        if net_qty != 0:
            symbol = p.get("symbol")
            entry_price = safe_float(p.get("entryPrice"), 0.0)
            side = "long" if net_qty > 0 else "short"
            result[symbol] = {
                "entry_price": entry_price,
                "side": side,
                "net_qty": net_qty,
                "pnlUnrealized": safe_float(p.get("pnlUnrealized"), 0.0),
                "unrealizedPnlPct": safe_float(p.get("unrealizedPnlPct"), 0.0),
                "trailingStopPct": safe_float(p.get("trailingStopPct"), 0.0),
                "durationSeconds": int(safe_float(p.get("durationSeconds"), 0.0))
            }
    return result

async def position_already_open(symbol: str):
    """
    Vérifie si une position est déjà ouverte pour le symbole.
    """
    positions = await get_real_positions()
    for pos in positions:
        if pos["symbol"] == symbol:
            return True
    return False

async def get_real_pnl(symbol, side, entry_price, amount, leverage):
    """
    Calcule le PnL réel d'une position.
    Retourne toujours un dict homogène avec :
    - pnl (USD brut)
    - pnl_usd (alias de pnl, pour compatibilité)
    - pnl_percent (% du PnL)
    - mark_price (dernier prix connu)
    """
    from utils.get_market import get_market

    market = await get_market(symbol)
    if not market:
        log(f"[WARN] Market data not found for {symbol}, using entry_price as mark_price")
        mark_price = entry_price
    else:
        mark_price = market.get("price") or entry_price

    # ✅ PnL en USD (brut)
    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
    else:  # short
        pnl_usd = (entry_price - mark_price) * amount

    # ✅ PnL en %
    if entry_price > 0:
        if side.lower() == "long":
            pnl_percent = (mark_price - entry_price) / entry_price * 100 * leverage
        else:
            pnl_percent = (entry_price - mark_price) / entry_price * 100 * leverage
    else:
        pnl_percent = 0.0

    return {
        "pnl": pnl_usd,             # alias pour compatibilité avec ancien code
        "pnl_usd": pnl_usd,         # valeur principale en USD
        "pnl_percent": pnl_percent, # en pourcentage
        "mark_price": mark_price    # dernier prix connu
    }

def safe_float(val, default=0.0):
    """Convertit val en float, même si c'est une string invalide ou vide."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def _get_first_float(d, keys, default=0.0):
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                pass
    return default

async def get_real_positions():
    """
    Récupère les positions ouvertes réelles depuis Backpack Exchange
    et les retourne sous forme de liste de dictionnaires.
    """
    try:
        raw_positions = account.get_open_positions()
    except Exception as e:
        log(f"[ERROR] Cannot fetch positions: {e}")
        return []

    positions_list = []

    for pos in raw_positions:
        try:
            net_qty = safe_float(pos.get("netQuantity"), 0.0)
            if net_qty == 0:
                continue  # ignorer les positions nulles

            side = "long" if net_qty > 0 else "short"
            entry_price = safe_float(pos.get("entryPrice"), 0.0)
            current_price = safe_float(pos.get("markPrice"), entry_price)  # fallback sur entry_price

            # Calcul PnL %
            if entry_price > 0:
                pnl = (current_price - entry_price) / entry_price * 100
                if side == "short":
                    pnl = -pnl
            else:
                pnl = 0.0

            amount = abs(net_qty)

            positions_list.append({
                "symbol": pos.get("symbol"),
                "side": side,
                "entry_price": entry_price,
                "current_price": current_price,
                "pnl": pnl,
                "amount": amount
            })

        except Exception as e:
            log(f"[WARNING] Failed to parse position {pos}: {e}")
            continue

    return positions_list