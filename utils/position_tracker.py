# utils/position_tracker.py
from config.settings import get_config
from utils.logger import log
from datetime import time

# Load configuration
config = get_config()

class PositionTracker:
    def __init__(self, symbol, direction, entry_price, amount, trailing_percent=0.002):
        """
        :param symbol: str - Nom du symbole (ex: BTC_USDC_PERP)
        :param direction: str - "long" ou "short"
        :param entry_price: float - Prix d'entrée
        :param amount: float - Quantité
        :param trailing_percent: float - ex: 0.002 = 0.2% trailing stop
        """
        self.symbol = symbol
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.amount = amount
        self.trailing_percent = trailing_percent
        self.open_time = time.time()

        self.trailing_stop = None
        self.max_price_seen = entry_price if self.direction == "long" else None
        self.min_price_seen = entry_price if self.direction == "short" else None
        self.is_closed = False
        self.close_time = None
        self.close_price = None

    def is_open(self):
        return not self.is_closed

    def get_unrealized_pnl(self, current_price):
        """Return current PnL %"""
        if self.direction == "long":
            return (current_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - current_price) / self.entry_price * 100

    def update_trailing_stop(self, current_price, timestamp=None):
        """Update trailing stop according to current price"""
        if not self.is_open():
            return

        if self.direction == "long":
            if self.max_price_seen is None or current_price > self.max_price_seen:
                self.max_price_seen = current_price
                self.trailing_stop = self.max_price_seen * (1 - self.trailing_percent)

        elif self.direction == "short":
            if self.min_price_seen is None or current_price < self.min_price_seen:
                self.min_price_seen = current_price
                self.trailing_stop = self.min_price_seen * (1 + self.trailing_percent)

    def should_close(self, current_price):
        """Check if trailing stop has been hit"""
        if not self.is_open() or self.trailing_stop is None:
            return False

        if self.direction == "long" and current_price <= self.trailing_stop:
            return True
        if self.direction == "short" and current_price >= self.trailing_stop:
            return True
        return False

    def close(self, current_price, timestamp=None):
        """Close position and return realized PnL %"""
        if not self.is_open():
            return None
        self.is_closed = True
        self.close_time = timestamp or time.time()
        self.close_price = current_price
        return self.get_unrealized_pnl(current_price)

    def get_status(self, current_price, timestamp=None):
        """
        Return a snapshot of position state:
        - PnL%
        - trailing stop
        - should_close
        """
        if not self.is_open():
            return None

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