import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import time
from execute.open_position_usdc import open_position
from list.orderbook_signal import get_orderbook_signal

# Nombre de niveaux à prendre en compte pour l'analyse
ORDERBOOK_DEPTH = 10
# Seuil de déclenchement d’un signal (ratio bid/ask ou ask/bid)
ASYMMETRY_THRESHOLD = 1.1
# Volume minimum cumulé bid+ask (en token)
MIN_TOTAL_VOLUME = 50

async def get_orderbook_signal(symbol: str) -> str:
    url = "wss://ws.backpack.exchange"

    async with websockets.connect(url) as ws:
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [f"depth.{symbol}"]
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"📡 Subscribed to depth.{symbol}")

        bids = []
        asks = []

        while True:
            message = await ws.recv()
            msg = json.loads(message)

            if 'data' in msg and msg['data'].get('e') == 'depth':
                data = msg['data']

                if 'b' in data:
                    bids += data['b']
                if 'a' in data:
                    asks += data['a']

                bids = bids[-ORDERBOOK_DEPTH:]
                asks = asks[-ORDERBOOK_DEPTH:]

                # Convert to float and sum
                bid_volume = sum(float(qty) for _, qty in bids)
                ask_volume = sum(float(qty) for _, qty in asks)

                print(f"📊 Bids: {bid_volume:.2f} | Asks: {ask_volume:.2f}")

                if (bid_volume + ask_volume) < MIN_TOTAL_VOLUME:
                    print("⚠️ Volume total trop faible")
                    return "HOLD"

                if bid_volume > ask_volume * ASYMMETRY_THRESHOLD:
                    return "BUY"
                elif ask_volume > bid_volume * ASYMMETRY_THRESHOLD:
                    return "SELL"
                else:
                    return "HOLD"

# Pour exécution directe
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 orderbook_signal.py <SYMBOL>")
        sys.exit(1)

    symbol = sys.argv[1]
    signal = asyncio.run(get_orderbook_signal(symbol))
    print(f"📢 Signal for {symbol}: {signal}")