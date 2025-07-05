from bpx.account import Account, OrderTypeEnum
import sys
import subprocess
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_open_positions(public_key: str, secret_key: str):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = account.get_open_positions()

    if not isinstance(positions, list):
        raise ValueError("Could not retrieve open positions.")
    return positions

def close_position_percent(public_key: str, secret_key: str, symbol: str, percent: float):
    if percent <= 0 or percent > 100:
        raise ValueError("Invalid percentage. Must be between 0 and 100.")

    positions = get_open_positions(public_key, secret_key)

    for position in positions:
        if position.get("symbol") != symbol:
            continue

        net_qty = float(position.get("netQuantity", "0"))
        if net_qty == 0:
            raise ValueError(f"No open position found for symbol '{symbol}'.")

        side = "SELL" if net_qty > 0 else "BUY"
        qty_to_close = abs(net_qty) * (percent / 100)

        print(f"Submitting MARKET {side} order for {qty_to_close:.6f} {symbol} ({percent:.0f}% of position)")

        account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type=OrderTypeEnum.MARKET,
            quantity=f"{qty_to_close:.6f}",
            reduce_only=True
        )

        print("Order response:", response)
        return

    raise ValueError(f"No position found for symbol '{symbol}'.")

def list_open_positions_script():
    script_path = os.path.join(os.path.dirname(__file__), "..", "list", "opened_positions.py")
    subprocess.run(["python3", script_path])

def main():
    if len(sys.argv) != 3:
        print("Usage: python close_position_percent.py <SYMBOL> <PERCENT>")
        print("Example: python close_position_percent.py SOL_USDC_PERP 50")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        percent = float(sys.argv[2])
    except ValueError:
        print("Error: Percent must be a number.")
        sys.exit(1)

    try:
        close_position_percent(public_key, secret_key, symbol, percent)
    except ValueError as e:
        print(f"Error: {e}")
        print(f"\nListing open positions...\n")
        list_open_positions_script()

if __name__ == "__main__":
    main()
