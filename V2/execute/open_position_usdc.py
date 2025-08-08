from bpx.account import Account
from bpx.public import Public
from tabulate import tabulate
import os
import sys
import math
from decimal import Decimal, ROUND_DOWN

from utils.logger import log
from utils.order_validator import is_order_valid_for_market, adjust_to_step
from utils.i18n import t

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def round_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step

def get_decimal_places(number_str):
    if "." not in number_str:
        return 0
    return len(number_str.split(".")[1].rstrip("0"))

def open_position(symbol: str, usdc_amount: float, direction: str, dry_run: bool = False):
    if direction.lower() not in ["long", "short"]:
        print(t("order.invalid_direction"))
        return

    if usdc_amount <= 0:
        print(t("order.invalid_amount"))
        return

    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    headers = ["Symbol", "Order type", "Quantity Executed/Ordered", "Amount Executed/Ordered", "Status"]
    table = []

    markets = public.get_markets()
    if not isinstance(markets, list):
        print(t("order.market_list_failed"))
        return

    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(t("order.symbol_not_found", symbol))
        return

    ticker = public.get_ticker(symbol)
    if not isinstance(ticker, dict):
        print(t("order.ticker_failed"))
        return

    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price == 0:
        print(t("order.invalid_price"))
        return

    quantity_filter = market_info.get("filters", {}).get("quantity", {})
    step_size = float(quantity_filter.get("stepSize", "1"))
    min_qty = float(quantity_filter.get("minQty", "0.000001"))
    tick_size = float(market_info.get("filters", {}).get("price", {}).get("tickSize", "0.01"))

    raw_quantity = usdc_amount / mark_price
    if step_size >= 1:
        quantity = int(raw_quantity // step_size * step_size)
    else:
        quantity = round_to_step(raw_quantity, step_size)

    quantity_decimals = get_decimal_places(quantity_filter.get("stepSize", "1"))
    tick_decimals = get_decimal_places(market_info.get("filters", {}).get("price", {}).get("tickSize", "0.01"))
    if step_size >= 1:
        quantity_str = str(int(quantity))
    else:
        quantity_str = f"{quantity:.{quantity_decimals}f}"

    log(t("order.market_info", symbol))
    log(f"   - markPrice: {mark_price:.{tick_decimals}f}")
    log(f"   - stepSize: {step_size}")
    log(f"   - minQty: {min_qty}")
    log(f"   - targetQuantity: {quantity_str}")

    if quantity < min_qty:
        print(t("order.below_min_qty", quantity_str, min_qty, symbol))
        print(t("order.increase_amount"))
        return

    # ✅ Vérification de la conformité (stepSize + tickSize)
    valid_qty, valid_price = is_order_valid_for_market(quantity, mark_price, step_size, tick_size)

    if not valid_qty or not valid_price:
        print(t("order.invalid_qty_or_price"))
        if not valid_qty:
            print(t("order.step_error", quantity, step_size))
            quantity = adjust_to_step(quantity, step_size)
        if not valid_price:
            print(t("order.tick_error", mark_price, tick_size))
            mark_price = adjust_to_step(mark_price, tick_size)

        if step_size >= 1:
            quantity_str = str(int(quantity))
        else:
            quantity_str = f"{quantity:.{quantity_decimals}f}"

        print(t("order.adjusted_qty", quantity))
        print(t("order.adjusted_price", mark_price, tick_decimals))

    side = "Bid" if direction.lower() == "long" else "Ask"
    order_type = "Market"

    if dry_run:
        print(t("order.dry_run", order_type, side, symbol, usdc_amount, quantity_str))
        return

    print(t("order.submitting", order_type, side, symbol, usdc_amount, quantity_str))

    response = account.execute_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        reduce_only=False
    )

    if not isinstance(response, dict):
        print(t("order.invalid_response"))
        return

    status = response.get("status", "UNKNOWN")
    executed_quantity = float(response.get("executedQuantity", 0))
    executed_quote_quantity = float(response.get("executedQuoteQuantity", 0))
    quote_quantity = usdc_amount

    table.append([
        symbol,
        side,
        f"{executed_quantity:.6f} / {quantity_str}",
        f"{executed_quote_quantity:.2f} / {quote_quantity:.2f}",
        status,
    ])

    print(t("order.response"))
    print(tabulate(table, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    dry_run = False
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    flags = [arg for arg in sys.argv[1:] if arg.startswith("--")]

    if "--dry-run" in flags:
        dry_run = True

    if len(args) != 3:
        print(t("order.usage"))
        sys.exit(1)

    symbol = args[0]
    try:
        usdc_amount = float(args[1])
    except ValueError:
        print(t("order.amount_must_be_number"))
        sys.exit(1)

    direction = args[2]

    open_position(symbol, usdc_amount, direction, dry_run=dry_run)
