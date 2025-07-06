from bpx.public import Public
from tabulate import tabulate

list_allmarkets = Public()

def get_markets():
    headers = ["Symbol"]
    table = []
    market = list_allmarkets.get_markets()
    for market in market:
        table.append([
            market['symbol'],
        ])

    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    get_markets()
