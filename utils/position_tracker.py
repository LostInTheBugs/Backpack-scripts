# utils/position_tracker.py
from config.settings import get_config
from utils.logger import log
from datetime import datetime

# Load configuration
config = get_config()

class PositionTracker:
    def __init__(self, symbol, direction, entry_price, quantity, open_time=None):
        self.symbol = symbol
        self.direction = direction  # "long" ou "short"
        self.entry_price = entry_price
        self.quantity = quantity
        self.open_time = open_time or datetime.utcnow()
        self.trailing_stop = None
        self.highest_price = entry_price if direction == "long" else None
        self.lowest_price = entry_price if direction == "short" else None
        self.closed = False

    def is_open(self):
        return not self.closed

    def get_unrealized_pnl(self, current_price):
        if self.direction == "long":
            return (current_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - current_price) / self.entry_price * 100

    def update_trailing_stop(self, current_price, timestamp=None):
        """Met à jour le trailing stop dynamiquement"""
        if self.direction == "long":
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price
                self.trailing_stop = self.highest_price * 0.99
        else:  # short
            if self.lowest_price is None or current_price < self.lowest_price:
                self.lowest_price = current_price
                self.trailing_stop = self.lowest_price * 1.01

    def should_close(self, current_price):
        """Vérifie si la position doit être fermée selon le trailing stop"""
        if self.trailing_stop is None:
            return False
        if self.direction == "long":
            return current_price <= self.trailing_stop
        else:
            return current_price >= self.trailing_stop

    def close(self, current_price, timestamp=None):
        """Ferme la position et retourne le PnL final"""
        pnl = self.get_unrealized_pnl(current_price)
        self.closed = True
        return pnl

    def get_status(self, current_price, timestamp=None):
        """Retourne un snapshot complet de l'état de la position"""
        if not self.is_open():
            return None

        # Met à jour trailing stop
        self.update_trailing_stop(current_price, timestamp)

        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "current_price": current_price,
            "pnl_pct": self.get_unrealized_pnl(current_price),
            "trailing_stop": self.trailing_stop,
            "should_close": self.should_close(current_price),
            "open_time": self.open_time,
        }
