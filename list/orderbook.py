import sys
import asyncio
from backpack_exchange_sdk.websocket import WebSocketClient

async def main(symbol: str, depth=5):
    ws = WebSocketClient()

    def handle_depth(msg):
        data = msg.get("data", {})
        print(f"\nTop {depth} BIDS:")
        for price, size in data.get("bids", [])[:depth]:
            print(f"  {price} | {size}")
        print("\nTop asks:")
        for price, size in data.get("asks", [])[:depth]:
            print(f"  {price} | {size}")

    ws.subscribe(streams=[f"depth.{symbol}"], callback=handle_depth)
    print(f"Subscribed to depth.{symbol}")
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python depth_stream.py SYMBOL")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
