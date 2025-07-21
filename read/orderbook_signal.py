import asyncio
import json
import sys
import websockets
from statistics import median

orderbook = {"bids": {}, "asks": {}}
symbol = sys.argv[1] if len(sys.argv) > 1 else "SOL_USDC"

async def listen_orderbook(symbol):
    url = "wss://ws.backpack.exchange"
    async with websockets.connect(url) as ws:
        stream = f"depth.{symbol}"
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream]
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"📡 Subscribed to {stream}")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if "data" in data:
                update_orderbook(data["data"])

async def print_stats():
    while True:
        bids = [(float(p), float(s)) for p, s in orderbook["bids"].items()]
        asks = [(float(p), float(s)) for p, s in orderbook["asks"].items()]

        if not bids or not asks:
            await asyncio.sleep(1)
            continue

        bid_prices, bid_sizes = zip(*bids)
        ask_prices, ask_sizes = zip(*asks)

        total_bid_token = sum(bid_sizes)
        total_ask_token = sum(ask_sizes)
        total_bid_usdc = sum(p * s for p, s in bids)
        total_ask_usdc = sum(p * s for p, s in asks)

        avg_bid_price = total_bid_usdc / total_bid_token
        avg_ask_price = total_ask_usdc / total_ask_token
        median_bid = median(bid_prices)
        median_ask = median(ask_prices)

        print(f"\n📊 Orderbook stats for {symbol}")
        print(f"🔵 Bids: {total_bid_token:.4f} Token (~{total_bid_usdc:.2f} USDC)")
        print(f"    Avg: {avg_bid_price:.4f} | Median: {median_bid:.4f}")
        print(f"🔴 Asks: {total_ask_token:.4f} Token (~{total_ask_usdc:.2f} USDC)")
        print(f"    Avg: {avg_ask_price:.4f} | Median: {median_ask:.4f}")

        ratio = total_bid_usdc / total_ask_usdc if total_ask_usdc else 0

        if ratio > 1.2:
            signal = "🟢 BUY SIGNAL"
        elif ratio < 0.8:
            signal = "🔴 SELL SIGNAL"
        else:
            signal = "⚪ NEUTRAL"

        print(f"📈 Signal: {signal} (Bid/Ask ratio = {ratio:.2f})")
        await asyncio.sleep(1)

def update_orderbook(data):
    for side in ["b", "a"]:
        levels = data.get(side, [])
        book_side = orderbook["bids"] if side == "b" else orderbook["asks"]
        for price_str, size_str in levels:
            price = price_str
            size = float(size_str)
            if size == 0:
                book_side.pop(price, None)
            else:
                book_side[price] = size

def get_orderbook_signal() -> str:
    """
    Basic signal decision based on bid/ask imbalance.

    Returns:
        - "BUY" if bids > asks by 20%
        - "SELL" if asks > bids by 20%
        - "NEUTRAL" otherwise
    """
    bids = [(float(p), float(s)) for p, s in orderbook.get("bids", {}).items()]
    asks = [(float(p), float(s)) for p, s in orderbook.get("asks", {}).items()]

    total_bid_volume = sum(s for _, s in bids)
    total_ask_volume = sum(s for _, s in asks)

    if total_bid_volume > 1.2 * total_ask_volume:
        return "BUY"
    elif total_ask_volume > 1.2 * total_bid_volume:
        return "SELL"
    else:
        return "NEUTRAL"

async def main():
    await asyncio.gather(
        listen_orderbook(symbol),
        print_stats()
    )

if __name__ == "__main__":
    asyncio.run(main())
