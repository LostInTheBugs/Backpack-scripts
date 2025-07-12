import sys
import os
import asyncio
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bpx.account import Account
from execute.open_position_usdc import open_position

from bpx.public import Public

public = Public()
account = Account(
    public_key=os.environ.get("bpx_bot_public_key"),
    secret_key=os.environ.get("bpx_bot_secret_key"),
    window=5000
)

def get_orderbook_signal(symbol: str, volume_threshold=50, sensitivity=1.1):
    """
    Récupère le carnet d'ordres et renvoie un signal 'BUY', 'SELL' ou 'HOLD'
    basé sur l'asymétrie des volumes bid/ask.
    """
    orderbook = public.get_orderbook(symbol, depth=10)
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    bid_volume = sum(float(bid[1]) for bid in bids)
    ask_volume = sum(float(ask[1]) for ask in asks)

    print(f"📊 Bids volume: {bid_volume:.2f} | Asks volume: {ask_volume:.2f}")

    total_volume = bid_volume + ask_volume
    if total_volume < volume_threshold:
        print(f"⚠️ Volume total trop faible ({total_volume:.2f}), pas de signal")
        return "HOLD"

    if bid_volume > ask_volume * sensitivity:
        return "BUY"
    elif ask_volume > bid_volume * sensitivity:
        return "SELL"
    else:
        return "HOLD"

def position_exists(symbol: str) -> bool:
    positions = account.get_open_positions()
    for p in positions:
        qty = float(p.get("quantity", 0))
        if p.get("symbol") == symbol and abs(qty) > 0:
            return True
    return False

async def run_bot(symbol, usdc_amount, interval, leverage):
    print(f"🔄 Starting bot for {symbol} with {usdc_amount} USDC | Interval: {interval}s | Leverage: x{leverage}")

    while True:
        try:
            signal = get_orderbook_signal(symbol)
            if signal in ["BUY", "SELL"]:
                if position_exists(symbol):
                    print(f"⚠️ Position already open on {symbol}, skipping new order.")
                else:
                    direction = "long" if signal == "BUY" else "short"
                    print(f"📈 Signal: {signal} - Opening {direction} position")
                    open_position(symbol, usdc_amount * leverage, direction)
            else:
                print(f"⏸️ No signal for {symbol}")

            await asyncio.sleep(interval)

        except Exception as e:
            print(f"⚠️ Error in bot loop: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 bot_orderbook.py <SYMBOL> <USDC_AMOUNT> [INTERVAL] [LEVERAGE]")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        usdc_amount = float(sys.argv[2])
    except ValueError:
        print("Invalid USDC amount.")
        sys.exit(1)

    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    leverage = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    asyncio.run(run_bot(symbol, usdc_amount, interval, leverage))
