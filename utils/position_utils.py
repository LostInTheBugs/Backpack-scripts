# utils/position_utils.py
import os
import asyncio
from bpx.account import Account
from utils.logger import log
from config.settings import get_config

# Charger la configuration
config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

log(f"[DEBUG] Using public_key={public_key}, secret_key={'***' if secret_key else None}")

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


async def get_real_positions():
    """Retourne une liste de positions ouvertes avec détails pour dashboard."""
    positions = await get_open_positions()
    positions_list = []

    for symbol, p in positions.items():
        net_qty = p["net_qty"]
        if net_qty != 0:
            entry_price = p["entry_price"]
            side = p["side"]
            pnl_pct = p["unrealizedPnlPct"]
            amount = abs(net_qty)
            duration_seconds = p.get("durationSeconds", 0)
            h = duration_seconds // 3600
            m = (duration_seconds % 3600) // 60
            s = duration_seconds % 60
            duration = f"{h}h{m}m{s}s" if h > 0 else f"{m}m{s}s"
            trailing_stop = p.get("trailingStopPct", 0.0)

            positions_list.append({
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "pnl": pnl_pct,
                "amount": amount,
                "duration": duration,
                "trailing_stop": trailing_stop
            })

    log(f"[INFO] Fetched {len(positions_list)} open positions from account")
    return positions_list
