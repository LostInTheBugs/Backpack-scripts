from bpx.account import Account
from tabulate import tabulate


import os
public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")


def main():
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = account.get_borrow_lend_positions()

    if not isinstance(positions, list):
        print(f"Error: {positions}")
        return


    
    table = []
    headers = ["Symbol", "Type", "Quantity", "Cumulative Interest"]

    for detail in positions:
        symbol = detail.get("symbol", "UNKNOWN")
        interest = float(detail.get("cumulativeInterest", "0"))
        net_qty  = float(detail.get("netQuantity", "0"))
        if net_qty != 0:
           pos_type = "LEND" if net_qty > 0 else "BORROW"


        table.append([
           symbol,
           pos_type,
           f"{abs(net_qty):.6f}",
           f"{abs(interest):.6f}",
        ])

    print("[Available borrow and lending positions]")
    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    main()
