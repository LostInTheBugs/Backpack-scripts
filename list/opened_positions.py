from bpx.account import Account
from tabulate import tabulate
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def get_open_positions(public_key: str, secret_key: str):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = account.get_open_positions()

    if not isinstance(positions, list):
        raise ValueError(f"❌ Failed to retrieve open positions: {positions}")
    
    return positions

def display_open_positions(positions: list):
    headers = [
        "Symbol",
        "Side",
        "Quantity",
        "Entry Price",
        "Est. Liq. Price",
        "PnL Unrealized",
        "PnL Realized"
    ]
    table = []

    for detail in positions:
        symbol = detail.get("symbol", "UNKNOWN")
        net_qty = float(detail.get("netQuantity", "0"))

        if net_qty == 0:
            continue

        side = "Long" if net_qty > 0 else "Short"
        entry_price = float(detail.get("entryPrice", "0"))
        liq_price = float(detail.get("estLiquidationPrice", "0"))
        pnl_unrealized = float(detail.get("pnlUnrealized", "0"))
        pnl_realized = float(detail.get("pnlRealized", "0"))

        pnl_unrealized_str = f"{pnl_unrealized:.2f}"
        if pnl_unrealized < 0:
            pnl_unrealized_str = f"{RED}{pnl_unrealized_str}{RESET}"
        elif pnl_unrealized > 0:
            pnl_unrealized_str = f"{GREEN}{pnl_unrealized_str}{RESET}"

        table.append([
            symbol,
            side,
            abs(net_qty),
            f"{entry_price:.6f}",
            f"{liq_price:.6f}",
            pnl_unrealized_str,
            f"{pnl_realized:.2f}",
        ])

    print("[Opened positions]")
    print(tabulate(table, headers=headers, tablefmt="grid"))

def main():
    try:
        positions = get_open_positions(public_key, secret_key)
        display_open_positions(positions)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
