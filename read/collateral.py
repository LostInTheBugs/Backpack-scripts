from bpx.account import Account
from tabulate import tabulate
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_collateral_data(public_key: str, secret_key: str):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    collateral_info = account.get_collateral()

    if not isinstance(collateral_info, dict):
        raise ValueError("No collateral data recovered")

    return collateral_info.get("collateral", [])

def display_collateral(collateral_list: list):
    if not collateral_list:
        print("No collateral positions found")
        return
    headers = [
        "Symbol",
        "lendQuantity",
        "collateralValue",
    ]
    table = []
    
    for detail in collateral_list:
        symbol = detail.get("symbol", "UNKNOWN")
        lend_qty = float(detail.get("lendQuantity", "0"))
        collateral_val = float(detail.get("collateralValue", "0"))

        if lend_qty > 0:
            table.append([
                symbol,
                lend_qty,
                f"{collateral_val} $",
        ])
            
    print("[Collateral used]")       
    print(tabulate(table, headers=headers, tablefmt="grid"))       

def main():
    try:
        collateral_list = get_collateral_data(public_key, secret_key)
        display_collateral(collateral_list)
    except Exception as e:
        print(f"Error : {e}")

if __name__ == "__main__":
    main()
