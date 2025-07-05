from bpx.account import Account, OrderTypeEnum
import sys
import subprocess

import os
public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")


def close_position_percent(symbol: str, percent: float):
    if percent <= 0 or percent > 100:
        print("Invalid percentage. Must be between 0 and 100.")
        return

    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = account.get_open_positions()

    if not isinstance(positions, list):
        print("Error: Could not retrieve open positions.")
        return

    # Cherche la position correspondante
    for position in positions:
        if position.get("symbol") != symbol:
            continue

        net_qty = float(position.get("netQuantity", "0"))
        if net_qty == 0:
            print("No open position found for this symbol.")
            return

        side = "SELL" if net_qty > 0 else "BUY"
        qty_to_close = abs(net_qty) * (percent / 100)

        print(f"? Submitting MARKET {side} order for {qty_to_close:.6f} {symbol} ({percent:.0f}% of position)")

        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type=OrderTypeEnum.MARKET,
            quantity=f"{qty_to_close:.6f}",
            reduce_only=True
        )

        print("Order response:", response)
        return

    print(f"❌ No position found for symbol '{symbol}'. Listing open positions...\n")
    script_path = os.path.join(os.path.dirname(__file__), "..", "list", "opened_positions.py")
    subprocess.run(["python3", script_path])


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python close_position_percent.py <SYMBOL> <PERCENT>")
        print("Exemple: python close_position_percent.py SOL_USDC_PERP 50")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        percent = float(sys.argv[2])
    except ValueError:
        print("Error: Percent must be a number.")
        sys.exit(1)

    close_position_percent(symbol, percent)
