from bpx.account import Account
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

def open_position(symbol: str, usdc_amount: float, direction: str, dry_run: bool = False):
    if direction.lower() not in ["long", "short"]:
        print("❌ Invalid direction. Use 'long' or 'short'.")
        return

    if usdc_amount <= 0:
        print("❌ USDC amount must be greater than zero.")
        return

    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    headers = ["Symbol", "Order type", "Quantity Executed/Ordered", "Amount Executed/Ordered", "Status"]
    table = []

    # Check if symbol exists
    markets = public.get_markets()
    if not isinstance(markets, list):
        print("❌ Failed to retrieve market list.")
        return

    if not any(m.get("symbol") == symbol for m in markets):
        print(f"❌ Symbol '{symbol}' not found in market list.")
        return

    # Get ticker for mark price
    ticker = public.get_ticker(symbol)
    if not isinstance(ticker, dict):
        print("❌ Failed to retrieve ticker data.")
        return

    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price == 0:
        print("❌ Invalid mark price from ticker.")
        return

    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(f"❌ Symbol '{symbol}' not found.")
        return 

    step_size_str = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "1")
    step_size = float(step_size_str)

    raw_quantity = usdc_amount / mark_price

    def round_quantity_to_step(quantity: float, step_size: float) -> float:
        return (quantity // step_size) * step_size

    quantity = round_quantity_to_step(raw_quantity, step_size)

    # Nombre de décimales à afficher selon step_size
    if '.' in step_size_str:
        step_size_decimals = len(step_size_str.split('.')[1].rstrip('0'))
    else:
        step_size_decimals = 0

    quantity_str = f"{quantity:.{step_size_decimals}f}"

    min_qty = float(market_info.get("filters", {}).get("quantity", {}).get("minQty", "0.00001"))
    step_size = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "N/A")

    print(f"📊 {symbol} market info:")
    print(f"   - markPrice: {mark_price}")
    print(f"   - stepSize: {step_size}")
    print(f"   - minQty: {min_qty}")
    print(f"   - targetQuantity: {quantity_str}")

    if quantity < min_qty:
        print(f"❌ Order quantity {quantity_str} is below the minimum allowed ({min_qty}) for {symbol}.")
        print(f"➡️ Increase your USDC amount or choose another symbol.")
        return

    side = "Bid" if direction.lower() == "long" else "Ask"
    order_type = "Market"

    if dry_run:
        print(f"[DRY RUN] Would submit {order_type} {side} order on {symbol} using {usdc_amount:.2f} USDC ≈ {quantity_str} units")
        return

    print(f"🚀 Submitting {order_type} {side} order on {symbol} using {usdc_amount:.2f} USDC ≈ {quantity_str} units")

    response = account.execute_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        reduce_only=False
    )

    if not isinstance(response, dict):
        print("❌ Invalid response from order execution.")
        return

    status = response.get("status", "UNKNOWN")
    executed_quantity = float(response.get("executedQuantity", 0))
    executed_quote_quantity = float(response.get("executedQuoteQuantity", 0))
    quote_quantity = usdc_amount  # montant USDC initial utilisé

    table.append([
        symbol,
        side,
        f"{executed_quantity:.6f} / {quantity_str}",
        f"{executed_quote_quantity:.2f} / {quote_quantity:.2f}",
        status,
    ])

    print("✅ Order response:")
    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    dry_run = False

    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    flags = [arg for arg in sys.argv[1:] if arg.startswith("--")]

    if "--dry-run" in flags:
        dry_run = True

    if len(args) != 3:
        print("Usage: python open_position_usdc.py <SYMBOL> <USDC_AMOUNT> <DIRECTION> [--dry-run]")
        print("Example: python open_position_usdc.py SOL_USDC_PERP 25 long --dry-run")
        sys.exit(1)

    symbol = args[0]
    try:
        usdc_amount = float(args[1])
    except ValueError:
        print("❌ USDC amount must be a number.")
        sys.exit(1)

    direction = args[2]

    open_position(symbol, usdc_amount, direction, dry_run=dry_run)
