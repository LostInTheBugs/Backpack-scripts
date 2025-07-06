from bpx.public import Public
from tabulate import tabulate
from datetime import datetime, timedelta, timezone

list_allmarkets = Public()

def get_markets():
    headers = ["Symbol", "Base Symbol", "Quote Symbol", "Market Type", "Order Book State", "Created At"]
    table = []

    current_time = datetime.now(timezone.utc)
    min_created_at = current_time - timedelta(hours=24)

    markets = list_allmarkets.get_markets()
    
    for market in markets:
        created_at_str = market.get("createdAt", "")
        try:
            created_at_dt = datetime.fromisoformat(created_at_str)
        except ValueError:
            continue

        if created_at_dt >= min_created_at:
            created_at_fmt = created_at_dt.strftime("%Y-%m-%d %H:%M:%S")
            table.append([
                market['symbol'],
                market['baseSymbol'],
                market['quoteSymbol'],
                market['marketType'],
                market['orderBookState'],
                created_at_fmt,
            ])

    if table:
        print("[Markets created in the last 24 hours]")
        print(tabulate(table, headers=headers, tablefmt="grid"))
    else:
        print("No markets created in the last 24 hours.")

if __name__ == "__main__":
    get_markets()
