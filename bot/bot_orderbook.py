import sys
import os
import asyncio
import time
from execute.open_position_usdc import open_position
from bpx.account import Account
from bpx.public import Public

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
public = Public()
account = Account(
    public_key=os.environ.get("bpx_bot_public_key"),
    secret_key=os.environ.get("bpx_bot_secret_key"),
)

async def get_orderbook_signal(symbol: str, sensitivity=1.1):
    """
    Analyse du carnet pour détecter un signal BUY / SELL / HOLD.
    Pas de seuil de volume, uniquement asymétrie.
    """
    orderbook = public.get_orderbook(symbol, depth=10)
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    bid_volume = sum(float(bid[1]) for bid in bids)
    ask_volume = sum(float(ask[1]) for ask in asks)

    print(f"📊 Bids volume: {bid_volume:.2f} | Asks volume: {ask_volume:.2f}")

    if bid_volume > ask_volume * sensitivity:
        return "BUY"
    elif ask_volume > bid_volume * sensitivity:
        return "SELL"
    else:
        return "HOLD"

async def run_bot(symbol, usdc_amount, interval, leverage):
    print(f"🤖 Bot started for {symbol} | Amount: {usdc_amount} USDC | Interval: {interval}s | Leverage: x{leverage}")

    while True:
        try:
            # Ne rien faire si une position est déjà ouverte
            positions = account.get_open_positions()
            active = next((p for p in positions if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0), None)
            if active:
                print(f"⏸️ Position already open on {symbol}, waiting...")
                await asyncio.sleep(interval)
                continue

            signal = await get_orderbook_signal(symbol)
            if signal == "BUY":
                print("📈 Signal: BUY")
                open_position(symbol, usdc_amount * leverage, "long")
            elif signal == "SELL":
                print("📉 Signal: SELL")
                open_position(symbol, usdc_amount * leverage, "short")
            else:
                print("⏸️ HOLD signal")

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
        print("❌ Invalid USDC amount.")
        sys.exit(1)

    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    leverage = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    try:
        asyncio.run(run_bot(symbol, usdc_amount, interval, leverage))
    except KeyboardInterrupt:
        print("👋 Bot stopped.")
