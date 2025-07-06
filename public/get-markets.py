from bpx.public import Public
from tabulate import tabulate

list_allmarkets = Public()

def get_markets():
    headers = ["Symbol", "Base Symbol", "Quote Symbol", "Market Type", "Filters", "IMF Function", "MMF Function", "Funding Interval", "Funding Rate Upper Bound", "Funding Rate Lower Bound", "Open Interest Limit", "Order Book State", "Created At"]
    table = []
    market = list_allmarkets.get_markets()
    for market in market:
        table.append([
            market['symbol'],
            market['baseSymbol'],
            market['quoteSymbol'],
            market['marketType'],
            market['filters'],
            market['imfFunction'],
            market['mmfFunction'],
            market['fundingInterval'],
            market['fundingRateUpperBound'],
            market['fundingRateLowerBound'],
            market['openInterestLimit'],
            market['orderBookState'],
            market['createdAt'],            
        ])

    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    get_markets()
