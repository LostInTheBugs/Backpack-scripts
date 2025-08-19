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

log(f"Using public_key={public_key}, secret_key={'***' if secret_key else None}", level="DEBUG")

# Création de l'objet Account central
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)


async def position_already_open(symbol: str) -> bool:
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
    try:
        positions = await asyncio.to_thread(account.get_open_positions)
        for position in positions:
            if position["symbol"] == symbol and float(position.get("netQuantity", 0)) != 0:
                pnl_unrealized = float(position.get("pnlUnrealized", 0))
                notional = float(position.get("netExposureNotional", 1))
                return pnl_unrealized, notional
        return 0.0, 1.0
    except Exception as e:
        log(f"⚠️ Erreur get_real_pnl({symbol}): {e}", level="error")
        return 0.0, 1.0

def get_open_positions():
    try:
        positions = account.get_open_positions()
        log(f"Retrieved {len(positions)} positions from API")
        return positions
    except Exception as e:
        log(f"[ERROR] ❌ Failed to fetch open positions: {e}")
        return []
    
async def get_real_positions():
    try:
        positions = await account.get_positions()  # <-- utilise l'objet existant
        positions_list = []

        for p in positions:
            if p.get("open", False):
                symbol = p.get("symbol")
                pnl = float(p.get("unrealized_pnl_pct", 0.0))
                amount = float(p.get("size", 0.0))
                duration_seconds = int(p.get("duration_seconds", 0))
                h = duration_seconds // 3600
                m = (duration_seconds % 3600) // 60
                s = duration_seconds % 60
                duration = f"{h}h{m}m{s}s" if h > 0 else f"{m}m{s}s"
                trailing_stop = float(p.get("trailing_stop_pct", 0.0))

                positions_list.append({
                    "symbol": symbol,
                    "pnl": pnl,
                    "amount": amount,
                    "duration": duration,
                    "trailing_stop": trailing_stop
                })

        log(f"[INFO] Fetched {len(positions_list)} open positions from account")
        return positions_list

    except Exception as e:
        log(f"[ERROR] Failed to fetch open positions: {e}", level="ERROR")
        return []