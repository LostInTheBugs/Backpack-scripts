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
        net_qty = float(p.get("netQuantity", 0))
        if net_qty != 0:
            symbol = p.get("symbol")
            entry_price = float(p.get("entryPrice", 0))
            side = "long" if net_qty > 0 else "short"
            result[symbol] = {
                "entry_price": entry_price,
                "side": side,
                "net_qty": net_qty,
                "pnlUnrealized": float(p.get("unrealizedPnl", 0.0)),
                "unrealizedPnlPct": float(p.get("unrealizedPnlPct", 0.0)),
                "trailingStopPct": float(p.get("trailingStopPct", 0.0)),
                "durationSeconds": int(p.get("durationSeconds", 0))
            }
    return result


async def position_already_open(symbol: str) -> bool:
    """Retourne True si une position est ouverte pour ce symbole."""
    positions = await get_open_positions()
    return symbol in positions


async def get_real_pnl(symbol: str):
    """Retourne le PnL non réalisé et la valeur notionnelle d'une position."""
    positions = await get_open_positions()
    pos = positions.get(symbol)
    if not pos:
        return 0.0, 1.0

    try:
        pnl_unrealized = float(pos.get("pnlUnrealized", 0.0))
        net_qty = float(pos.get("net_qty", 1.0))
        notional = abs(net_qty) * float(pos.get("entry_price", 1.0))
        return pnl_unrealized, notional
    except Exception as e:
        log(f"[ERROR] get_real_pnl({symbol}): {e}", level="ERROR")
        return 0.0, 1.0


def safe_float(val, default=0.0):
    """Convertit val en float, même si c'est une string invalide ou vide."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

async def get_real_positions(account=None) -> List[Dict[str, Any]]:
    if account is None:
        from .position_utils import account as default_account
        account = default_account
    try:
        raw_positions = await account.get_open_positions()
    except Exception as e:
        log(f"[ERROR] Impossible de récupérer les positions : {e}", level="ERROR")
        return []

    positions_list = []

    for pos in raw_positions:
        net_qty = safe_float(pos.get("netQuantity", 0))
        if net_qty == 0:
            continue

        entry_price = safe_float(pos.get("entryPrice", 0))
        pnl_usdc = safe_float(pos.get("pnlUnrealized", 0))
        notional = abs(net_qty) * entry_price
        pnl_percent = (pnl_usdc / notional * 100) if notional != 0 else 0.0

        side = "long" if net_qty > 0 else "short"
        trailing_stop = safe_float(pos.get("trailingStopPct", 0.0))
        duration_seconds = int(pos.get("durationSeconds", 0))

        # Formatage durée en h m s
        h = duration_seconds // 3600
        m = (duration_seconds % 3600) // 60
        s = duration_seconds % 60
        duration = f"{h}h{m}m{s}s" if h > 0 else f"{m}m{s}s"

        positions_list.append({
            "symbol": pos.get("symbol", "UNKNOWN"),
            "side": side,
            "entry_price": entry_price,
            "pnl": pnl_percent,
            "amount": abs(net_qty),
            "duration": duration,
            "trailing_stop": trailing_stop
        })

    log(f"Fetched {len(positions_list)} open positions from account", level="DEBUG")
    return positions_list