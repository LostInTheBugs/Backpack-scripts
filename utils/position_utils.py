# utils/position_utils.py
import os
import asyncio
from datetime import datetime
from bpx.account import Account
from utils.logger import log
from config.settings import get_config
from typing import List, Dict, Any, Optional

config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

log(f"Using public_key={public_key}, secret_key={'***' if secret_key else None}", level="DEBUG")

account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)

# Cache pour stocker le PnL connu
last_known_pnl: Dict[str, Dict[str, Any]] = {}

def update_pnl_cache(symbol: str, pnl_usdc: float, pnl_percent: float):
    last_known_pnl[symbol] = {
        "pnl_usdc": pnl_usdc,
        "pnl_percent": pnl_percent,
        "timestamp": datetime.now()
    }

def get_cached_pnl(symbol: str) -> Optional[Dict]:
    return last_known_pnl.get(symbol)

def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        log(f"[WARNING] Could not convert to float: {val}, using default: {default}", level="WARNING")
        return default

def _get_first_float(d, keys, default=0.0):
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                log(f"[WARNING] Invalid float value for key {k}: {d[k]}", level="WARNING")
                continue
    return default

async def get_raw_positions(retry_count: int = 3, delay: float = 0.5):
    for attempt in range(retry_count):
        try:
            if attempt > 0:
                await asyncio.sleep(delay * attempt)
            positions = account.get_open_positions()
            if positions is None:
                log(f"[WARNING] API returned None for positions, attempt {attempt + 1}", level="WARNING")
                continue
            log(f"[DEBUG] Fetched {len(positions)} raw positions", level="DEBUG")
            return positions
        except Exception as e:
            log(f"[ERROR] Failed to fetch positions (attempt {attempt + 1}/{retry_count}): {e}", level="ERROR")
            if attempt == retry_count - 1:
                log("[ERROR] All retry attempts failed, returning empty list", level="ERROR")
                return []
            await asyncio.sleep(delay * (attempt + 1))
    return []

async def get_open_positions() -> Dict[str, Dict[str, Any]]:
    positions = await get_raw_positions()
    result = {}
    for p in positions:
        try:
            net_qty = safe_float(p.get("netQuantity", 0))
            if net_qty == 0:
                continue
            symbol = p.get("symbol")
            if not symbol:
                log("[WARNING] Position without symbol", level="WARNING")
                continue
            entry_price = _get_first_float(p, ["entryPrice", "avgEntryPrice"], 0.0)
            side = "long" if net_qty > 0 else "short"
            pnl_unrealized = _get_first_float(p, ["unrealizedPnl", "pnlUnrealized"], None)
            pnl_pct = _get_first_float(p, ["unrealizedPnlPct"], 0.0)
            trailing_stop = safe_float(p.get("trailingStopPct", 0.0))
            duration_seconds = int(p.get("durationSeconds", 0))
            h, m, s = duration_seconds // 3600, (duration_seconds % 3600) // 60, duration_seconds % 60
            duration = f"{h}h{m}m{s}s" if h else f"{m}m{s}s"
            result[symbol] = {
                "entry_price": entry_price,
                "side": side,
                "net_qty": net_qty,
                "pnlUnrealized": pnl_unrealized,
                "unrealizedPnlPct": pnl_pct,
                "trailingStopPct": trailing_stop,
                "durationSeconds": duration_seconds,
                "duration": duration
            }
        except Exception as e:
            log(f"[ERROR] Error processing position {p}: {e}", level="ERROR")
            continue
    return result

async def get_real_positions() -> List[Dict[str, Any]]:
    raw_positions = await get_raw_positions()
    positions_list = []
    default_leverage = getattr(config.trading, "leverage", 1)

    for pos in raw_positions:
        try:
            net_qty = safe_float(pos.get("netQuantity", 0))
            if net_qty == 0:
                continue
            symbol = pos.get("symbol", "UNKNOWN")
            entry_price = _get_first_float(pos, ["entryPrice", "avgEntryPrice"], 0.0)
            mark_price = _get_first_float(pos, ["markPrice", "indexPrice", "lastPrice"], entry_price)
            leverage = int(_get_first_float(pos, ["leverage"], default_leverage)) or 1
            notional = abs(net_qty) * entry_price
            margin = notional / leverage if leverage else notional

            pnl_usdc = _get_first_float(pos, ["unrealizedPnl", "pnlUnrealized"], None)
            if pnl_usdc is None:
                cached = get_cached_pnl(symbol)
                if cached and (datetime.now() - cached["timestamp"]).seconds < 60:
                    pnl_usdc = cached["pnl_usdc"]
                    log(f"[DEBUG] Using cached PnL for {symbol}: {pnl_usdc}", level="DEBUG")
                else:
                    # fallback calculé
                    if net_qty > 0:
                        pnl_usdc = (mark_price - entry_price) * net_qty
                    else:
                        pnl_usdc = (entry_price - mark_price) * abs(net_qty)
                    log(f"[WARNING] Calculated fallback PnL for {symbol}: {pnl_usdc}", level="WARNING")

            pnl_percent = (pnl_usdc / margin * 100) if margin else 0.0
            if net_qty > 0:
                ret_pct = ((mark_price - entry_price) / entry_price * 100) if entry_price else 0.0
            else:
                ret_pct = ((entry_price - mark_price) / entry_price * 100) if entry_price else 0.0

            side = "long" if net_qty > 0 else "short"
            trailing_stop = safe_float(pos.get("trailingStopPct", 0.0))
            duration_seconds = int(pos.get("durationSeconds", 0))
            h, m, s = duration_seconds // 3600, (duration_seconds % 3600) // 60, duration_seconds % 60
            duration = f"{h}h{m}m{s}s" if h else f"{m}m{s}s"

            update_pnl_cache(symbol, pnl_usdc, pnl_percent)

            positions_list.append({
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "pnl": pnl_percent,
                "pnl_usdc": pnl_usdc,
                "ret_pct": ret_pct,
                "amount": abs(net_qty),
                "duration": duration,
                "trailing_stop": trailing_stop,
                "leverage": leverage
            })

        except Exception as e:
            log(f"[ERROR] Error processing position {pos.get('symbol', 'UNKNOWN')}: {e}", level="ERROR")
            continue

    log(f"Processed {len(positions_list)} open positions", level="DEBUG")
    return positions_list

async def position_already_open(symbol: str) -> bool:
    positions = await get_open_positions()
    return symbol in positions

def get_real_pnl(symbol: str, side: str, entry_price: float, amount: float, leverage: float = 1.0) -> dict:
    """
    Calcul du PnL réel en USDC et en % pour une position.
    """
    from utils.get_market import get_market
    mark_price = get_market(symbol)["price"]
    if mark_price is None or mark_price == 0:
        mark_price = entry_price  # fallback

    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
    else:  # short
        pnl_usd = (entry_price - mark_price) * amount

    pnl_percent = (pnl_usd / (entry_price * amount)) * leverage * 100
    return {"pnl_usd": pnl_usd, "pnl_percent": pnl_percent}