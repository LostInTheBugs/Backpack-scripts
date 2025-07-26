import asyncio
import websockets
import json
import sys
from tabulate import tabulate

async def listen_orderbook(symbol):
    url = "wss://ws.backpack.exchange"
    orderbook = {"bids": {}, "asks": {}}

    async with websockets.connect(url) as ws:
        stream_name = f"depth.{symbol}"
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream_name],
            "id": 1
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"Subscribed to {stream_name}")

        async def print_orderbook():
            while True:
                # Get top 5 bids and asks sorted by price
                top_bids = sorted(orderbook["bids"].items(), key=lambda x: float(x[0]), reverse=True)[:5]
                top_asks = sorted(orderbook["asks"].items(), key=lambda x: float(x[0]))[:5]

                total_bid_token = sum(float(size) for _, size in top_bids)
                total_ask_token = sum(float(size) for _, size in top_asks)
                total_bid_usdc = sum(float(price)*float(size) for price, size in top_bids)
                total_ask_usdc = sum(float(price)*float(size) for price, size in top_asks)

                table = []
                for i in range(5):
                    bid_price, bid_size = top_bids[i] if i < len(top_bids) else ("", "")
                    ask_price, ask_size = top_asks[i] if i < len(top_asks) else ("", "")
                    table.append([bid_price, bid_size, "", ask_price, ask_size])

                headers = ["Bid Price (USDC)", "Bid Size (Token)", "", "Ask Price (USDC)", "Ask Size (Token)"]
                print(f"\nOrderbook for {symbol} | Depth: 5")
                print(f"🔵 Total Bid: {total_bid_token:.4f} Token (~{total_bid_usdc:.2f} USDC)")
                print(f"🔴 Total Ask: {total_ask_token:.4f} Token (~{total_ask_usdc:.2f} USDC)\n")
                print(tabulate(table, headers=headers, tablefmt="grid"))

                await asyncio.sleep(1)

        # Launch printing concurrently
        asyncio.create_task(print_orderbook())

        # Listen to incoming WS messages
        while True:
            message = await ws.recv()
            msg = json.loads(message)
            data = msg.get("data", {})
            bids = data.get("b", [])
            asks = data.get("a", [])

            # Update bids
            for price, size in bids:
                if float(size) == 0:
                    orderbook["bids"].pop(price, None)
                else:
                    orderbook["bids"][price] = size

            # Update asks
            for price, size in asks:
                if float(size) == 0:
                    orderbook["asks"].pop(price, None)
                else:
                    orderbook["asks"][price] = size

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orderbook.py SYMBOL")
        sys.exit(1)
    try:
        asyncio.run(listen_orderbook(sys.argv[1]))
    except KeyboardInterrupt:
        print("\nBye!")
