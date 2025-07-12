import asyncio
import websockets
import json
import sys
from statistics import median

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

        async def print_stats():
            while True:
                # Convert prices and sizes to floats lists for bids and asks
                bid_prices = [float(price) for price in orderbook["bids"].keys()]
                bid_sizes = [float(size) for size in orderbook["bids"].values()]
                ask_prices = [float(price) for price in orderbook["asks"].keys()]
                ask_sizes = [float(size) for size in orderbook["asks"].values()]

                # Total volumes (token)
                total_bid_token = sum(bid_sizes)
                total_ask_token = sum(ask_sizes)

                # Total volumes in USDC (price * size)
                total_bid_usdc = sum(p * s for p, s in zip(bid_prices, bid_sizes))
                total_ask_usdc = sum(p * s for p, s in zip(ask_prices, ask_sizes))

                # Weighted average price = sum(price*size)/sum(size)
                avg_bid_price = (total_bid_usdc / total_bid_token) if total_bid_token else 0
                avg_ask_price = (total_ask_usdc / total_ask_token) if total_ask_token else 0

                # Median price
                median_bid_price = median(bid_prices) if bid_prices else 0
                median_ask_price = median(ask_prices) if ask_prices else 0

                print(f"\nOrderbook stats for {symbol}")
                print(f"🔵 Bids: total volume = {total_bid_token:.4f} Token (~{total_bid_usdc:.2f} USDC)")
                print(f"    Weighted avg price = {avg_bid_price:.4f} USDC")
                print(f"    Median price = {median_bid_price:.4f} USDC")
                print(f"🔴 Asks: total volume = {total_ask_token:.4f} Token (~{total_ask_usdc:.2f} USDC)")
                print(f"    Weighted avg price = {avg_ask_price:.4f} USDC")
                print(f"    Median price = {median_ask_price:.4f} USDC")

                await asyncio.sleep(3)

        # Run print_stats concurrently
        asyncio.create_task(print_stats())

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
