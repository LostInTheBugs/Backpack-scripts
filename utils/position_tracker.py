from config.settings import get_config
from utils.logger import log

# Load configuration
config = get_config()

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
        else:  # SELL
            self.trailing_stop = price * (1 + self.trailing_stop_pct)
        
        log(f" [{self.symbol}] 🟢 Position opened {direction} at {price:.4f} ({timestamp})", level="INFO")

    def update_trailing_stop(self, price, timestamp):
        """Update trailing stop based on current price"""
        if not self.is_open():
            return

        if self.direction == "BUY":
            # For long positions, trailing stop moves up with price
            new_stop = price * (1 - self.trailing_stop_pct)
            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop
        elif self.direction == "SELL":
            # For short positions, trailing stop moves down with price
            new_stop = price * (1 + self.trailing_stop_pct)
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

        log(f"[{self.symbol}] 🔴 Position closed {self.direction} at {price:.4f} ({timestamp}) | PnL: {pnl_pct:.2f}%", level="INFO")

        # Reset position state
        self.entry_price = None
        self.direction = None
        self.trailing_stop = None
        self.open_time = None

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