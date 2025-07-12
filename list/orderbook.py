import asyncio
import websockets
import json
import sys

async def listen_orderbook(symbol):
    url = "wss://ws.backpack.exchange"
    async with websockets.connect(url) as ws:
        stream_name = f"depth.{symbol}"  # format exact doc officielle
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": 1
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"Subscribed to {stream_name}")

        while True:
            response = await ws.recv()
            data = json.loads(response)
            print("Received:", data)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orderbook.py SYMBOL")
        sys.exit(1)
    asyncio.run(listen_orderbook(sys.argv[1]))
