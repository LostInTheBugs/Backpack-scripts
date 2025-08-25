# utils/position_tracker.py
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
    """
    from utils.get_market import get_market

    market = await get_market(symbol)
    if not market:
        log(f"Market data not found for {symbol}, using entry_price as mark_price", level="WARNING")
        mark_price = entry_price
    else:
        mark_price = safe_float(market.get("price"), entry_price)

    # ✅ PnL USD (sans leverage car amount est déjà la taille réelle)
    if side.lower() == "long":
        pnl_usd = (mark_price - entry_price) * amount
    else:  # short
        pnl_usd = (entry_price - mark_price) * amount

    # ✅ PnL % (SANS leverage - le leverage est déjà dans le calcul du margin)
    pnl_percent = 0.0
    if entry_price > 0:
        if side.lower() == "long":
            pnl_percent = (mark_price - entry_price) / entry_price * 100  # ✅ SANS leverage
        else:
            pnl_percent = (entry_price - mark_price) / entry_price * 100   # ✅ SANS leverage

    return {
        "pnl": pnl_usd,             
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
