import sys
import os
import asyncio
import json
import time
import websockets

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bpx.account import Account
from execute.open_position_usdc import open_position

account = Account(
    public_key=os.environ.get("bpx_bot_public_key"),
    secret_key=os.environ.get("bpx_bot_secret_key"),
    window=5000
)

orderbook = {"bids": {}, "asks": {}}

def position_exists(symbol: str) -> bool:
    positions = account.get_open_positions()
    for p in positions:
        if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0:
            return True
    return False

def get_orderbook_signal(symbol: str, sensitivity=1.1):
    """
    Analyse l'ordre book pour déterminer un signal 'BUY', 'SELL' ou 'HOLD'
    en fonction de l'asymétrie entre les volumes bids/asks.
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
    

async def bot_orderbook(symbol, usdc_amount, interval, leverage):
    url = "wss://ws.backpack.exchange"
    stream_name = f"depth.{symbol}"
    subscribe_msg = {
        "method": "SUBSCRIBE",
        "params": [stream_name],
        "id": 1
    }

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps(subscribe_msg))
        print(f"✅ Subscribed to {stream_name}")

        while True:
            try:
                msg = json.loads(await ws.recv())
                data = msg.get("data", {})
                bids = data.get("b", [])
                asks = data.get("a", [])

                # Update orderbook
                for price, size in bids:
                    if float(size) == 0:
                        orderbook["bids"].pop(price, None)
                    else:
                        orderbook["bids"][price] = float(size)

                for price, size in asks:
                    if float(size) == 0:
                        orderbook["asks"].pop(price, None)
                    else:
                        orderbook["asks"][price] = float(size)

                # Chaque interval, décision de trading
                signal = get_orderbook_signal()
                if signal in ["BUY", "SELL"]:
                    if position_exists(symbol):
                        print(f"⚠️ Position already open on {symbol}, skipping.")
                    else:
                        direction = "long" if signal == "BUY" else "short"
                        print(f"🚀 Opening {direction.upper()} position on {symbol}")
                        open_position(symbol, usdc_amount * leverage, direction)
                else:
                    print("⏸️ HOLD signal")

                await asyncio.sleep(interval)

            except Exception as e:
                print(f"⚠️ Error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 bot_orderbook.py <SYMBOL> <USDC_AMOUNT> [INTERVAL] [LEVERAGE]")
        sys.exit(1)

    symbol = sys.argv[1]
    usdc_amount = float(sys.argv[2])
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    leverage = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    try:
        asyncio.run(bot_orderbook(symbol, usdc_amount, interval, leverage))
    except KeyboardInterrupt:
        print("👋 Bot stopped.")
