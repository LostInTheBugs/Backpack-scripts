from bpx.account import Account, OrderTypeEnum
from bpx.public import Public
from tabulate import tabulate
import math
import os
import sys

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_step_size_decimals(market_info):
    step_size = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "1")
    if '.' in step_size:
        return len(step_size.split(".")[1].rstrip("0"))
    return 0


def open_position(symbol: str, usdc_amount: float, direction: str):
    if direction.lower() not in ["long", "short"]:
        print("❌ Invalid direction. Use 'long' or 'short'.")
        return

    if usdc_amount <= 0:
        print("❌ USDC amount must be greater than zero.")
        return

    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    table = []
    headers = ["Symbol", "Order type", "Quantity Executed/Ordered", "Amount Executed/Ordered", "Status"]

    # Check if symbol exists
    markets = public.get_markets()
    if not isinstance(markets, list):
        print("❌ Failed to retrieve market list.")
        return

    if not any(m.get("symbol") == symbol for m in markets):
        print(f"❌ Symbol '{symbol}' not found in market list.")
        return

    # Now fetch ticker to get actual mark price
    ticker = public.get_ticker(symbol)
    
    if not isinstance(ticker, dict):
        print("❌ Failed to retrieve ticker data.")
        return

    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price == 0:
        print("❌ Invalid mark price from ticker.")
        return

    #quantity = f"{round(usdc_amount / mark_price, 4):.4f}"
    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
       print(f"❌ Symbol '{symbol}' not found.")
       return 
    step_size_str = market_info["filters"]["quantity"]["stepSize"]
    step_size_decimals = get_step_size_decimals(market_info)
    quantity = round(usdc_amount / mark_price, step_size_decimals)
    quantity_str = f"{quantity:.{step_size_decimals}f}"
    
    
    side = "Bid" if direction.lower() == "long" else "Ask"
    order_type="Market"

    print(f"⏳ Submitting {order_type} {side} order on {symbol} using {usdc_amount} USDC ≈ {quantity} units")

    response = account.execute_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        reduce_only=False
    )


    table.append([
          symbol,
          side,
          f"{executedQuantity} / {quantity}",
          f"{executedQuoteQuantity} / {quoteQuantity}",
          status,
    ])

    print("✅ Order response:")
    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python open_position_usdc.py <SYMBOL> <USDC_AMOUNT> <DIRECTION>")
        print("Example: python open_position_usdc.py SOL_USDC_PERP 25 long")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        usdc_amount = float(sys.argv[2])
    except ValueError:
        print("❌ USDC amount must be a number.")
        sys.exit(1)

    direction = sys.argv[3]
    open_position(symbol, usdc_amount, direction)
