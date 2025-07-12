import sys
import os
import asyncio
import json
import websockets
from execute.open_position_usdc import open_position
from bpx.account import Account

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

account = Account(
    public_key=os.environ.get("bpx_bot_public_key"),
    secret_key=os.environ.get("bpx_bot_secret_key"),
)

async def get_signal_from_orderbook(symbol: str, sensitivity=1.1):
    url = "wss://ws.backpack.exchange"
    stream_name = f"depth.{symbol}"
    orderbook = {"bids": {}, "asks": {}}

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": 1
        }))
        print(f"✅ Subscribed to {stream_name}")

        while True:
            msg = json.loads(await ws.recv())
            data = msg.get("data", {})
            bids = data.get("b", [])
            asks = data.get("a", [])

            for price, size in bids:
                if float(size) == 0:
                    orderbook["bids"].pop(price, None)
                else:
                    orderbook["bids"][price] = size
            for price, size in asks:
                if float(size) == 0:
                    orderbook["asks"].pop(price, None)
                else:
                    orderbook["asks"][price] = size

            # Calcule les volumes totaux
            bid_volume = sum(float(size) for size in orderbook["bids"].values())
            ask_volume = sum(float(size) for size in orderbook["asks"].values())
            print(f"📊 Bids volume: {bid_volume:.2f} | Asks volume: {ask_volume:.2f}")

            if bid_volume > ask_volume * sensitivity:
                return "BUY"
            elif ask_volume > bid_volume * sensitivity:
                return "SELL"
            else:
                return "HOLD"

async def run_bot(symbol: str, usdc_amount: float, interval: int, leverage: float):
    print(f"🤖 Bot started for {symbol} | Amount: {usdc_amount} USDC | Interval: {interval}s | Leverage: x{leverage}")

    while True:
        try:
            # Vérifie si une position est déjà ouverte
            positions = account.get_open_positions()
            active = next((p for p in positions if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0), None)
            if active:
                print(f"⏸️ Position already open on {symbol}, waiting...")
                await asyncio.sleep(interval)
                continue

            signal = await get_signal_from_orderbook(symbol)
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
