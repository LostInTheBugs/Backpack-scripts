import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import time
from execute.open_position_usdc import open_position
from list.orderbook_signal import get_orderbook_signal

async def run_bot(symbol, usdc_amount, interval, leverage):
    print(f"🔄 Starting bot for {symbol} with {usdc_amount} USDC | Interval: {interval}s | Leverage: x{leverage}")

    while True:
        try:
            signal = get_orderbook_signal(symbol)
            if signal == "BUY":
                print("📈 Signal: BUY")
                open_position(symbol, usdc_amount * leverage, "long")
            elif signal == "SELL":
                print("📉 Signal: SELL")
                open_position(symbol, usdc_amount * leverage, "short")
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
