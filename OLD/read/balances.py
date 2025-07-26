from bpx.account import Account
from tabulate import tabulate
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_account_balances(public_key: str, secret_key: str):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    balances = account.get_balances()

    if not isinstance(balances, dict):
        raise ValueError(f"Error retrieving balances : {balances}")
    
    return balances

def display_balances(balances: dict):
    headers = ["Symbol", "Available", "Locked", "Staked"]
    table = []

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

def main():
    try:
        balances = get_account_balances(public_key, secret_key)
        display_balances(balances)
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    main()
