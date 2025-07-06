from bpx.public import Public
from tabulate import tabulate

list_allmarkets = Public()

def get_markets():
    market = list_allmarkets.get_markets()
    for market in market:
        print(f"{market['symbol']}")

if __name__ == "__main__":
    get_markets()
