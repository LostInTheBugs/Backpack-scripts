# utils/position_utils.py
from config.settings import get_config
from utils.logger import log
import os
from bpx.account import Account
from utils.logger import log
from config.settings import get_config
from typing import List, Dict

config = get_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

log(f"Using public_key={public_key}, secret_key={'***' if secret_key else None}", level="DEBUG")

# Création de l'objet Account central
account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)

# Load configuration 


class PositionTracker:
    def __init__(self, symbol, trailing_stop_pct=None):
        self.symbol = symbol
        # Use config value if not specified
        if trailing_stop_pct is None:
            trailing_stop_pct = config.trading.trailing_stop_trigger
        self.trailing_stop_pct = trailing_stop_pct / 100  # Convert % to decimal (1% => 0.01)
        self.entry_price = None
        self.direction = None  # 'BUY' or 'SELL'
        self.trailing_stop = None
        self.open_time = None
        self.max_price = None  # For LONG positions
        self.min_price = None  # For SHORT positions

    def is_open(self):
        """Check if position is currently open"""
        return self.entry_price is not None

    def open(self, direction, price, timestamp):
        """Open a new position"""
        self.entry_price = price
        self.direction = direction
        self.open_time = timestamp
        
        # Set initial trailing stop
        if direction == "BUY":
            self.trailing_stop = price * (1 - self.trailing_stop_pct)
            self.max_price = price
        else:  # SELL
            self.trailing_stop = price * (1 + self.trailing_stop_pct)
            self.min_price = price
        
        log(f"[{self.symbol}] 🟢 Position opened {direction} at {price:.4f} ({timestamp})", level="DEBUG")

    def update_trailing_stop(self, price, timestamp):
        """Update trailing stop based on current price and best price reached"""
        if not self.is_open():
            return

        if self.direction == "BUY":
            # Update max price reached
            self.max_price = max(self.max_price, price)
            new_stop = self.max_price * (1 - self.trailing_stop_pct)
            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop

        elif self.direction == "SELL":
            # Update min price reached
            self.min_price = min(self.min_price, price)
            new_stop = self.min_price * (1 + self.trailing_stop_pct)
            if new_stop < self.trailing_stop:
                self.trailing_stop = new_stop

    def should_close(self, price):
        """Check if position should be closed based on trailing stop"""
        if not self.is_open():
            return False

        if self.direction == "BUY" and price <= self.trailing_stop:
            return True
        if self.direction == "SELL" and price >= self.trailing_stop:
            return True
        return False

    def close(self, price, timestamp):
        """Close the position and calculate PnL"""
        if not self.is_open():
            return 0

        # Calculate PnL percentage
        pnl_pct = 0
        if self.direction == "BUY":
            pnl_pct = ((price - self.entry_price) / self.entry_price) * 100
        elif self.direction == "SELL":
            pnl_pct = ((self.entry_price - price) / self.entry_price) * 100

        log(f"[{self.symbol}] 🔴 Position closed {self.direction} at {price:.4f} ({timestamp}) | PnL: {pnl_pct:.2f}%", level="DEBUG")

        # Reset position state
        self.entry_price = None
        self.direction = None
        self.trailing_stop = None
        self.open_time = None
        self.max_price = None
        self.min_price = None

        return pnl_pct

    def get_position_info(self):
        """Get current position information"""
        if not self.is_open():
            return None
        
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'trailing_stop': self.trailing_stop,
            'trailing_stop_pct': self.trailing_stop_pct * 100,
            'open_time': self.open_time
        }

    def get_unrealized_pnl(self, current_price):
        """Calculate unrealized PnL based on current price"""
        if not self.is_open():
            return 0
        
        if self.direction == "BUY":
            return ((current_price - self.entry_price) / self.entry_price) * 100
        elif self.direction == "SELL":
            return ((self.entry_price - current_price) / self.entry_price) * 100
        
        return 0
    

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
    ✅ CORRECTION FINALE: Utiliser PnL total (realized + unrealized)
    """
    try:
        entry_price = safe_float(raw_pos.get("entryPrice"), 0.0)
        mark_price = safe_float(raw_pos.get("markPrice"), entry_price)
        net_qty = safe_float(raw_pos.get("netQuantity"), 0.0)
        
        # ✅ CORRECTION: PnL TOTAL = realized + unrealized
        pnl_realized = safe_float(raw_pos.get("pnlRealized"), 0.0)
        pnl_unrealized = safe_float(raw_pos.get("pnlUnrealized"), 0.0)
        pnl_total = pnl_realized + pnl_unrealized  # 🎯 C'EST ÇA LE FIX !

        if net_qty == 0:
            return {}

        # Déterminer le sens de la position
        side = "long" if net_qty > 0 else "short"

        # ✅ UTILISER LE PnL TOTAL
        pnl_usd = pnl_total
        
        # Calcul du PnL % basé sur le PnL total
        notional = abs(net_qty) * entry_price
        if notional > 0:
            pnl_percent = (pnl_total / notional) * 100
        else:
            pnl_percent = 0.0

        # ✅ Log pour vérification
        log(f"[PARSE] {raw_pos.get('symbol')}: PnL_realized=${pnl_realized:.3f} + PnL_unrealized=${pnl_unrealized:.3f} = Total=${pnl_total:.3f}", level="DEBUG")

        return {
            "symbol": raw_pos.get("symbol"),
            "entry_price": entry_price,
            "mark_price": mark_price,
            "side": side,
            "amount": abs(net_qty),
            "pnl_usd": pnl_usd,           # ✅ PnL TOTAL
            "pnl_pct": pnl_percent,       # ✅ % basé sur PnL TOTAL
            "leverage": safe_float(raw_pos.get("leverage", 1), 1.0),
            "pnl_realized": pnl_realized,     # ✅ Garder pour debug
            "pnl_unrealized": pnl_unrealized  # ✅ Garder pour debug
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
    ✅ SIMPLIFICATION: Utiliser directement les données de parse_position
    """
    try:
        # Récupérer la position depuis l'API plutôt que recalculer
        positions = await get_open_positions()
        pos = positions.get(symbol)
        
        if pos:
            # ✅ Utiliser directement les données parsées qui sont correctes
            return {
                "pnl": pos["pnl_usd"],
                "pnl_usd": pos["pnl_usd"],
                "pnl_percent": pos["pnl_pct"],
                "mark_price": pos["mark_price"]
            }
        else:
            # ✅ Fallback si position non trouvée
            log(f"Position not found for {symbol}, using manual calculation", level="WARNING")
            from utils.get_market import get_market
            
            market = await get_market(symbol)
            mark_price = safe_float(market.get("price"), entry_price) if market else entry_price

            # Calcul manuel simple
            if side.lower() == "long":
                pnl_usd = (mark_price - entry_price) * amount
                pnl_percent = (mark_price - entry_price) / entry_price * 100
            else:  # short
                pnl_usd = (entry_price - mark_price) * amount
                pnl_percent = (entry_price - mark_price) / entry_price * 100

            return {
                "pnl": pnl_usd,
                "pnl_usd": pnl_usd,
                "pnl_percent": pnl_percent,
                "mark_price": mark_price
            }
            
    except Exception as e:
        log(f"[ERROR] get_real_pnl failed for {symbol}: {e}", level="ERROR")
        return {"pnl": 0.0, "pnl_usd": 0.0, "pnl_percent": 0.0, "mark_price": entry_price}

async def debug_pnl_calculation(symbol, side, entry_price, amount, leverage, mark_price):
    """
    Debug détaillé du calcul de PnL pour identifier les problèmes
    """
    log(f"[DEBUG PnL] {symbol} {side}:", level="INFO")
    log(f"  Entry Price: {entry_price:.6f}", level="INFO")
    log(f"  Mark Price: {mark_price:.6f}", level="INFO")
    log(f"  Amount (from API): {amount:.6f}", level="INFO")
    log(f"  Leverage: {leverage}", level="INFO")
    
    # Calcul PnL USD
    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
        price_diff = mark_price - entry_price
    else:  # short
        pnl_usd = (entry_price - mark_price) * amount
        price_diff = entry_price - mark_price
    
    log(f"  Price Diff: {price_diff:.6f}", level="INFO")
    log(f"  PnL USD (calculated): {pnl_usd:.6f}", level="INFO")
    
    # Calcul PnL %
    if entry_price > 0:
        if side.lower() == "long":
            pnl_percent = (mark_price - entry_price) / entry_price * 100
        else:
            pnl_percent = (entry_price - mark_price) / entry_price * 100
    else:
        pnl_percent = 0.0
    
    log(f"  PnL % (calculated): {pnl_percent:.2f}%", level="INFO")
    
    # Vérification de cohérence
    notional = amount * entry_price
    expected_pnl_usd = notional * (pnl_percent / 100)
    
    log(f"  Notional (amount * entry): {notional:.2f}", level="INFO")
    log(f"  Expected PnL USD: {expected_pnl_usd:.6f}", level="INFO")
    log(f"  Difference: {abs(pnl_usd - expected_pnl_usd):.6f}", level="INFO")
    
    return {
        "pnl_usd": pnl_usd,
        "pnl_percent": pnl_percent,
        "mark_price": mark_price,
        "debug_info": {
            "notional": notional,
            "expected_pnl_usd": expected_pnl_usd,
            "price_diff": price_diff
        }
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
