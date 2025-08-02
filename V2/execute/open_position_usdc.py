from bpx.account import Account
from bpx.public import Public
from tabulate import tabulate
import os
import sys
import math

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def round_to_step(value: float, step: float) -> float:
    """Arrondit vers le bas à la précision du step donné"""
    return math.floor(value / step) * step

def get_decimal_places(number_str):
    """Retourne le nombre de décimales significatives dans une string"""
    if "." not in number_str:
        return 0
    return len(number_str.split(".")[1].rstrip("0"))

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

    # Récupération des marchés
    markets = public.get_markets()
    if not isinstance(markets, list):
        print("❌ Failed to retrieve market list.")
        return

    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(f"❌ Symbol '{symbol}' not found.")
        return

    # Récupération du mark price
    ticker = public.get_ticker(symbol)
    if not isinstance(ticker, dict):
        print("❌ Failed to retrieve ticker data.")
        return

    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price == 0:
        print("❌ Invalid mark price from ticker.")
        return

    # Paramètres de precision
    quantity_filter = market_info.get("filters", {}).get("quantity", {})
    step_size = float(quantity_filter.get("stepSize", "1"))
    min_qty = float(quantity_filter.get("minQty", "0.000001"))

    tick_size = float(market_info.get("filters", {}).get("price", {}).get("tickSize", "0.01"))

    # Calcul de la quantité
    raw_quantity = usdc_amount / mark_price
    quantity = round_to_step(raw_quantity, step_size)

    # Formatage lisible
    quantity_decimals = get_decimal_places(quantity_filter.get("stepSize", "1"))
    tick_decimals = get_decimal_places(market_info.get("filters", {}).get("price", {}).get("tickSize", "0.01"))
    quantity_str = f"{quantity:.{quantity_decimals}f}"

    print(f"📊 {symbol} market info:")
    print(f"   - markPrice: {mark_price:.{tick_decimals}f}")
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
    quote_quantity = usdc_amount  # montant initial prévu

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
