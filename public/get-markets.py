from bpx import API

api = API()

def get_markets():
    markets = api.get_markets()
    for market in markets:
        print(f"{market['name']:15} | {market['status']:8} | base: {market['baseAssetSymbol']}, quote: {market['quoteAssetSymbol']}")
        
if __name__ == "__main__":
    get_markets()
