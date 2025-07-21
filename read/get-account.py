from bpx.account import Account
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_account_info(public_key: str, secret_key: str):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    info = account.get_account()

    if not isinstance(info, dict):
        raise ValueError("Failed to retrieve account information")

    return info

def display_account_info(info: dict):
    mapping = {
        "autoBorrowSettlements": "Auto loan settlement",
        "autoLend": "Auto lending",
        "autoRealizePnl": "Auto PnL realization",
        "autoRepayBorrows": "Auto loan repayment",
        "borrowLimit": "Borrow limit (USD)",
        "futuresMakerFee": "Futures Maker fee (bps)",
        "futuresTakerFee": "Futures Taker fee (bps)",
        "leverageLimit": "Max leverage",
        "limitOrders": "Max limit orders",
        "liquidating": "Currently liquidating",
        "positionLimit": "Position limit (USD)",
        "spotMakerFee": "Spot Maker fee (bps)",
        "spotTakerFee": "Spot Taker fee (bps)",
        "triggerOrders": "Max trigger orders"
    }

    print("[Backpack Account Information]\n")
    print(f"{'Name':<35} | Value")
    print("-" * 55)
    for key, label in mapping.items():
        value = info.get(key, "—")
        print(f"{label:<35} | {value}")

def main():
    try:
        info = get_account_info(public_key, secret_key)
        display_account_info(info)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
