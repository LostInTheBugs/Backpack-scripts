import sys
from bpx.public import Public

def fetch_orderbook(symbol: str, depth: int = 10) -> dict:
    """
    Fetch the order book for a given trading pair from Backpack.
    """
    client = Public()
    try:
        orderbook = client.get_orderbook(symbol=symbol, limit=depth)
        return orderbook
    except Exception as e:
        print(f"Error fetching order book: {e}")
        return {}

def display_orderbook(orderbook: dict, depth: int = 5):
    """
    Print the top levels of the order book (asks and bids).
    """
    print(f"\nTop {depth} BIDS:")
    for price, size in orderbook.get("bids", [])[:depth]:
        print(f"  {price} | {size}")

    print(f"\nTop {depth} ASKS:")
    for price, size in orderbook.get("asks", [])[:depth]:
        print(f"  {price} | {size}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_orderbook.py SYMBOL")
        sys.exit(1)

    symbol = sys.argv[1]  # Example: SOL_USDC
    orderbook = fetch_orderbook(symbol)

    if orderbook:
        display_orderbook(orderbook, depth=5)
