import asyncio
import websockets
import json
import sys

async def listen_orderbook(symbol):
    # Conversion _ → -
    symbol_ws = symbol.replace("_", "-")
    url = "wss://stream.backpack.exchange/ws"
    async with websockets.connect(url) as ws:
        # S'abonner au canal depth.<symbol>
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [f"depth.{symbol_ws}"],
            "id": 1
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"Subscribed to depth.{symbol_ws}")

        while True:
            response = await ws.recv()
            data = json.loads(response)
            if "data" in data:
                bids = data["data"].get("bids", [])
                asks = data["data"].get("asks", [])
                if bids or asks:
                    print(f"Bids top: {bids[:3]}")
                    print(f"Asks top: {asks[:3]}")
                else:
                    print("Received empty orderbook update")
            else:
                # Message de confirmation ou autre
                print(f"Message: {data}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ws.py SYMBOL")
        sys.exit(1)
    asyncio.run(listen_orderbook(sys.argv[1]))
