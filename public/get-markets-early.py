from bpx.public import Public
from tabulate import tabulate
from datetime import datetime, timedelta, timezone

list_allmarkets = Public()

def get_markets():
    headers = ["Symbol", "Base Symbol", "Quote Symbol", "Market Type", "Order Book State", "Created At"]
    table = []

    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    twenty_four_hours = 24 * 60 * 60 * 1000
    min_created_at = current_time - twenty_four_hours


    market = list_allmarkets.get_markets()
    
    for market in market:
        created_at = market.get("createdAt", 0)
        if created_at >= min_created_at:
            created_at = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            table.append([
                market['symbol'],
                market['baseSymbol'],
                market['quoteSymbol'],
                market['marketType'],
                market['orderBookState'],
                market['createdAt'],     
            ])

    if table:
        print("[Markets created in the last 24 hours]")
        print(tabulate(table, headers=headers, tablefmt="grid"))
    else:
        print("No markets created in the last 24 hours.")


if __name__ == "__main__":
    get_markets()
