from bpx.account import Account

import os
public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")


def main():
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    colaterales = account.get_collateral()
    
    if not isinstance(colaterales, dict):
        print(f"No collateral data found")
        return
    collateral_list = colaterales.get("collateral", [])


    if not collateral_list:
        print("No collateral entries found")
        return

    print("[Collateral used]")
    for detail in collateral_list:
        symbol = detail.get("symbol", "UNKNOWN")
        lend_qty = float(detail.get("lendQuantity", "0"))
        collateral_val = float(detail.get("collateralValue", "0"))
        if lend_qty > 0:
           print(f" - {symbol}: lendQuantity={lend_qty:.6f}, collateralValue=${collateral_val:.2f}")
                                        


if __name__ == "__main__":
    main()
