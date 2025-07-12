import sys
import asyncio
from backpack_exchange_sdk.websocket import WebSocketClient
from tabulate import tabulate

def compute_total_volume(levels):
    return sum(float(qty) for price, qty in levels)

def format_orderbook_table(bids, asks, depth=5):
    table = []
    for i in range(depth):
        bid = bids[i] if i < len(bids) else ["", ""]
        ask = asks[i] if i < len(asks) else ["", ""]
        table.append([
            f"{bid[0]}", f"{bid[1]}", "|", f"{ask[0]}", f"{ask[1]}"
        ])
    return table

async def stream_orderbook(symbol: str, depth: int = 5):
    ws = WebSocketClient()

    def on_depth(msg):
        data = msg.get("data", {})
        bids = data.get("bids", [])[:depth]
        asks = data.get("asks", [])[:depth]

        total_bid = compute_total_volume(bids)
        total_ask = compute_total_volume(asks)

        table = format_orderbook_table(bids, asks, depth=depth)
        headers = ["Bid Price", "Bid Size", "", "Ask Price", "Ask Size"]

        print("\033c", end="")  # Clear terminal (Unix-like)
        print(f"Orderbook for {symbol} | Depth: {depth}")
        print(f"🔵 Total Bid Volume: {total_bid:.2f}")
        print(f"🔴 Total Ask Volume: {total_ask:.2f}\n")
        print(tabulate(table, headers=headers, tablefmt="grid"))

    ws.subscribe([f"depth.{symbol}"], callback=on_depth)

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orderbook_ws.py SYMBOL")
        sys.exit(1)
    
    symbol = sys.argv[1]  # Ex: SOL_USDC
    asyncio.run(stream_orderbook(symbol))
