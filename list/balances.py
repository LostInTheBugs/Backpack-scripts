from bpx.account import Account
from tabulate import tabulate

import os
public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def main():
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    balances = account.get_balances()

    if not isinstance(balances, dict):
        print(f"Error: {balances}")
        return
    
    table = []
    headers = ["Symbol", "Available", "Locked", "Staked"]

    for symbol, detail in balances.items():
        token_available = float(detail.get("available", "0"))
        token_locked = float(detail.get("locked", "0"))
        token_staked = float(detail.get("staked", "0"))


        table.append([
            symbol,
            f"{token_available:.6f}",
            f"{token_locked:.6f}",
            f"{token_staked:.2f}",
        ])

    print("[Available balances]")
    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    main()
