# utils/position_utils.py
import os
import asyncio
from datetime import datetime
from bpx.account import Account
from utils.logger import log
from config.settings import get_config
from typing import List, Dict, Any, Optional

# Charger la configuration
config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

log(f"Using public_key={public_key}, secret_key={'***' if secret_key else None}", level="DEBUG")

# Création de l'objet Account central
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)

# Cache pour conserver les dernières valeurs PnL connues
last_known_pnl = {}
last_update_time = {}

def update_pnl_cache(symbol: str, pnl_usdc: float, pnl_percent: float):
    """Met à jour le cache avec les dernières valeurs PnL connues"""
    last_known_pnl[symbol] = {
        'pnl_usdc': pnl_usdc,
        'pnl_percent': pnl_percent,
        'timestamp': datetime.now()
    }

def get_cached_pnl(symbol: str) -> Optional[Dict]:
    """Retourne la dernière valeur PnL connue pour un symbole"""
    return last_known_pnl.get(symbol)

async def get_raw_positions(retry_count: int = 3, delay: float = 0.5):
    """Récupère toutes les positions depuis l'API Backpack avec retry logic."""
    for attempt in range(retry_count):
        try:
            # Ajouter un petit délai pour éviter le rate limiting
            if attempt > 0:
                await asyncio.sleep(delay * attempt)
            
            positions = account.get_open_positions()
            
            if positions is None:
                log(f"[WARNING] API returned None for positions, attempt {attempt + 1}", level="WARNING")
                continue
                
            log(f"[DEBUG] Successfully fetched {len(positions)} raw positions", level="DEBUG")
            return positions
            
        except Exception as e:
            log(f"[ERROR] Failed to fetch positions (attempt {attempt + 1}/{retry_count}): {e}", level="ERROR")
            if attempt == retry_count - 1:
                log("[ERROR] All retry attempts failed, returning empty list", level="ERROR")
                return []
            await asyncio.sleep(delay * (attempt + 1))
    
    return []

async def get_open_positions():
    """Retourne un dict {symbol: {entry_price, side, net_qty}} pour les positions ouvertes."""
    positions = await get_raw_positions()
    result = {}
    
    for p in positions:
        try:
            net_qty = float(p.get("netQuantity", 0))
            if net_qty == 0:
                continue
                
            symbol = p.get("symbol")
            if not symbol:
                log("[WARNING] Position without symbol found", level="WARNING")
                continue
                
            entry_price = float(p.get("entryPrice", 0))
            side = "long" if net_qty > 0 else "short"
            
            # Vérification des valeurs PnL avec logging détaillé
            pnl_unrealized = p.get("unrealizedPnl")
            pnl_pct = p.get("unrealizedPnlPct")
            
            log(f"[DEBUG] {symbol}: unrealizedPnl={pnl_unrealized}, unrealizedPnlPct={pnl_pct}", level="DEBUG")
            
            result[symbol] = {
                "entry_price": entry_price,
                "side": side,
                "net_qty": net_qty,
                "pnlUnrealized": safe_float(pnl_unrealized, 0.0),
                "unrealizedPnlPct": safe_float(pnl_pct, 0.0),
                "trailingStopPct": float(p.get("trailingStopPct", 0.0)),
                "durationSeconds": int(p.get("durationSeconds", 0))
            }
            
        except Exception as e:
            log(f"[ERROR] Error processing position {p}: {e}", level="ERROR")
            continue
    
    return result

async def position_already_open(symbol: str) -> bool:
    """Retourne True si une position est ouverte pour ce symbole."""
    positions = await get_open_positions()
    return symbol in positions

async def get_real_pnl(symbol: str):
    """Retourne (unrealized_pnl_usdc, notional, margin, leverage) pour une position."""
    positions = await get_open_positions()
    pos = positions.get(symbol)
    
    if not pos:
        log(f"[DEBUG] No position found for {symbol}", level="DEBUG")
        return 0.0, 1.0, 1.0, 1

    try:
        net_qty = float(pos.get("net_qty", 0.0))
        entry_price = float(pos.get("entry_price", 0.0))
        notional = abs(net_qty) * entry_price
        lev = getattr(config.trading, "leverage", 1)
        margin = notional / lev if lev > 0 else notional

        # Récupération du PnL avec fallback sur le cache
        pnl_unrealized = pos.get("pnlUnrealized")
        
        if pnl_unrealized is None or pnl_unrealized == 0.0:
            # Vérifier le cache avant de calculer manuellement
            cached = get_cached_pnl(symbol)
            if cached and (datetime.now() - cached['timestamp']).seconds < 30:  # Cache valide 30s
                log(f"[DEBUG] Using cached PnL for {symbol}: {cached['pnl_usdc']}", level="DEBUG")
                return cached['pnl_usdc'], notional, margin, lev
            else:
                log(f"[WARNING] PnL unavailable for {symbol}, API returned: {pnl_unrealized}", level="WARNING")
                # Retourner la dernière valeur connue plutôt que 0
                if cached:
                    return cached['pnl_usdc'], notional, margin, lev
        else:
            pnl_unrealized = float(pnl_unrealized)
            # Mettre à jour le cache
            pnl_percent = (pnl_unrealized / margin * 100) if margin != 0 else 0.0
            update_pnl_cache(symbol, pnl_unrealized, pnl_percent)
            
        return pnl_unrealized, notional, margin, lev
        
    except Exception as e:
        log(f"[ERROR] get_real_pnl({symbol}): {e}", level="ERROR")
        # Utiliser le cache en cas d'erreur
        cached = get_cached_pnl(symbol)
        if cached:
            log(f"[DEBUG] Using cached PnL due to error for {symbol}", level="DEBUG")
            return cached['pnl_usdc'], 1.0, 1.0, 1
        return 0.0, 1.0, 1.0, 1

def safe_float(val, default=0.0):
    """Convertit val en float, même si c'est une string invalide ou vide."""
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

async def get_real_positions(account=None) -> List[Dict[str, Any]]:
    """
    Retourne la liste des positions ouvertes avec PnL calculé à partir du prix réel du marché.
    """
    from .get_market import get_market  # Import local pour récupérer le prix actuel

    if account is None:
        from .position_utils import account as default_account
        account = default_account

    try:
        raw_positions = await get_raw_positions()
    except Exception as e:
        log(f"[ERROR] Impossible de récupérer les positions : {e}", level="ERROR")
        return []

    positions_list = []
    default_leverage = getattr(config.trading, "leverage", 1)

    for pos in raw_positions:
        try:
            net_qty = safe_float(pos.get("netQuantity", 0))
            if net_qty == 0:
                continue

            symbol = pos.get("symbol", "UNKNOWN")
            entry_price = _get_first_float(pos, ["entryPrice", "avgEntryPrice"], 0.0)
            leverage = int(_get_first_float(pos, ["leverage"], default_leverage)) or 1
            side = "long" if net_qty > 0 else "short"

            # Récupération du prix réel du marché
            try:
                mark_price = _get_first_float(get_market(symbol), ["price"], entry_price)
            except Exception:
                mark_price = entry_price
                log(f"[WARNING] Could not fetch market price for {symbol}, using entry price", level="WARNING")

            # Calcul du PnL réel
            if side == "long":
                pnl_usdc = (mark_price - entry_price) * net_qty
                ret_pct = ((mark_price - entry_price) / entry_price * 100) if entry_price else 0.0
            else:
                pnl_usdc = (entry_price - mark_price) * abs(net_qty)
                ret_pct = ((entry_price - mark_price) / entry_price * 100) if entry_price else 0.0

            notional = abs(net_qty) * entry_price
            margin = notional / leverage if leverage > 0 else notional
            pnl_percent = (pnl_usdc / margin * 100) if margin != 0 else 0.0

            # Durée et trailing stop
            duration_seconds = int(pos.get("durationSeconds", 0))
            h = duration_seconds // 3600
            m = (duration_seconds % 3600) // 60
            s = duration_seconds % 60
            duration = f"{h}h{m}m{s}s" if h > 0 else f"{m}m{s}s"

            trailing_stop = safe_float(pos.get("trailingStopPct", 0.0))

            # Mise à jour du cache
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

    log(f"[DEBUG] Successfully processed {len(positions_list)} open positions", level="DEBUG")
    return positions_list
