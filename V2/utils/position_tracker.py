from utils.logger import log

class PositionTracker:
    def __init__(self, symbol, trailing_stop_pct=1.0):
        self.symbol = symbol
        self.trailing_stop_pct = trailing_stop_pct / 100  # Ex: 1% => 0.01
        self.entry_price = None
        self.direction = None  # 'BUY' ou 'SELL'
        self.trailing_stop = None
        self.open_time = None

    def is_open(self):
        return self.entry_price is not None

    def open(self, direction, price, timestamp):
        self.entry_price = price
        self.direction = direction
        self.open_time = timestamp
        if direction == "BUY":
            self.trailing_stop = price * (1 - self.trailing_stop_pct)
        else:
            self.trailing_stop = price * (1 + self.trailing_stop_pct)
        log(f"[{self.symbol}] 🟢 Position ouverte {direction} à {price:.4f} ({timestamp})")

    def update_trailing_stop(self, price, timestamp):
        if not self.is_open():
            return

        if self.direction == "BUY":
            new_stop = price * (1 - self.trailing_stop_pct)
            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop
        elif self.direction == "SELL":
            new_stop = price * (1 + self.trailing_stop_pct)
            if new_stop < self.trailing_stop:
                self.trailing_stop = new_stop

    def should_close(self, price):
        if not self.is_open():
            return False

        if self.direction == "BUY" and price <= self.trailing_stop:
            return True
        if self.direction == "SELL" and price >= self.trailing_stop:
            return True
        return False

    def close(self, price, timestamp):
        if not self.is_open():
            return 0

        pnl_pct = 0
        if self.direction == "BUY":
            pnl_pct = ((price - self.entry_price) / self.entry_price) * 100
        elif self.direction == "SELL":
            pnl_pct = ((self.entry_price - price) / self.entry_price) * 100

        log(f"[{self.symbol}] 🔴 Fermeture position {self.direction} à {price:.4f} ({timestamp}) | PnL: {pnl_pct:.2f}%")

        self.entry_price = None
        self.direction = None
        self.trailing_stop = None
        self.open_time = None

        return pnl_pct
