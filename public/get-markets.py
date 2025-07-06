from bpx.public import Public

list_allmarkets = Public()

def get_markets():
    markets = list_allmarkets.get_markets()
    for market in markets:
        print(f"{market['name']:15} | {market['status']:8} | base: {market['baseAssetSymbol']}, quote: {market['quoteAssetSymbol']}")

if __name__ == "__main__":
    get_markets()
