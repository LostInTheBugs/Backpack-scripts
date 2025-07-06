from bpx.account import Account
from tabulate import tabulate
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_borrow_lend_positions(public_key: str, secret_key: str):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = account.get_borrow_lend_positions()

    if not isinstance(positions, list):
        raise ValueError(f"Error when retrieving positions: {positions}")
    
    return positions

def display_borrow_lend_positions(positions: list):
    headers = ["Symbol", "Type", "Quantity", "Cumulative Interest"]
    table = []

    for detail in positions:
        symbol = detail.get("symbol", "UNKNOWN")
        interest = float(detail.get("cumulativeInterest", "0"))
        net_qty = float(detail.get("netQuantity", "0"))

        if net_qty == 0:
            continue 

        pos_type = "LEND" if net_qty > 0 else "BORROW"

        table.append([
            symbol,
            pos_type,
            f"{abs(net_qty):.6f}",
            f"{abs(interest):.6f} $",
        ])

    print("[Available borrow and lending positions]")
    print(tabulate(table, headers=headers, tablefmt="grid"))

def main():
    try:
        positions = get_borrow_lend_positions(public_key, secret_key)
        display_borrow_lend_positions(positions)
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    main()
