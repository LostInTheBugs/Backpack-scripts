import asyncio
import sys
from ..execute.open_position_usdc import open_position
from list.orderbook_signal import analyze_orderbook_signal

async def run_bot(symbol, usdc_amount):
    print(f"🔄 Starting bot for {symbol} with {usdc_amount} USDC")
    
    while True:
        try:
            signal = await analyze_orderbook_signal(symbol)

            if signal == "BUY":
                print("Signal is BUY  opening long position.")
                open_position(symbol, usdc_amount, "long")
            elif signal == "SELL":
                print("Signal is SELL  opening short position.")
                open_position(symbol, usdc_amount, "short")
            else:
                print("Signal is HOLD  no action taken.")

            await asyncio.sleep(10)  # Pause avant la prochaine analyse

        except Exception as e:
            print(f"Error in bot loop: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python bot_orderbook.py <SYMBOL> <USDC_AMOUNT>")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        usdc_amount = float(sys.argv[2])
    except ValueError:
        print("USDC amount must be a valid number.")
        sys.exit(1)

    asyncio.run(run_bot(symbol, usdc_amount))
