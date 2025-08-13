import math
import os
from decimal import Decimal
from tabulate import tabulate
import asyncio

from bpx.account import Account
from bpx.public import Public

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

async def open_position(symbol: str, usdc_amount: float, direction: str, dry_run: bool = False):
    if direction.lower() not in ["long", "short"]:
        log(t("order.invalid_direction"))
        return

    if usdc_amount <= 0:
        log(t("order.invalid_amount"))
        return

    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    headers = ["Symbol", "Order type", "Quantity Executed/Ordered", "Amount Executed/Ordered", "Status"]
    table = []

    # Récupération des marchés et ticker dans un thread pour éviter blocage
    markets = await asyncio.to_thread(public.get_markets)
    if not isinstance(markets, list):
        log(t("order.market_list_failed"))
        return

    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        log(t("order.symbol_not_found", symbol))
        return

    ticker = await asyncio.to_thread(public.get_ticker, symbol)
    mark_price = float(ticker.get("lastPrice", 0))
    if mark_price == 0:
        log(t("order.invalid_price"))
        return

    quantity_filter = market_info.get("filters", {}).get("quantity", {})
    step_size = float(quantity_filter.get("stepSize", "1"))
    min_qty = float(quantity_filter.get("minQty", "0.000001"))
    tick_size = float(market_info.get("filters", {}).get("price", {}).get("tickSize", "0.01"))

    raw_quantity = usdc_amount / mark_price
    quantity = round_to_step(raw_quantity, step_size) if step_size < 1 else int(raw_quantity // step_size * step_size)

    quantity_decimals = get_decimal_places(quantity_filter.get("stepSize", "1"))
    tick_decimals = get_decimal_places(market_info.get("filters", {}).get("price", {}).get("tickSize", "0.01"))
    quantity_str = f"{quantity:.{quantity_decimals}f}" if step_size < 1 else str(int(quantity))

    log(t("[INFO] order.market_info", symbol), level="INFO")
    log(f"   - markPrice: {mark_price:.{tick_decimals}f}", level="INFO")
    log(f"   - stepSize: {step_size}", level="INFO")
    log(f"   - minQty: {min_qty}", level="INFO")
    log(f"   - targetQuantity: {quantity_str}", level="INFO")

    if quantity < min_qty:
        log(t("order.below_min_qty", quantity_str, min_qty, symbol), level="INFO")
        log(t("order.increase_amount"), level="INFO")
        return

    valid_qty, valid_price = is_order_valid_for_market(quantity, mark_price, step_size, tick_size)
    if not valid_qty or not valid_price:
        if not valid_qty:
            quantity = adjust_to_step(quantity, step_size)
        if not valid_price:
            mark_price = adjust_to_step(mark_price, tick_size)

    side = "Bid" if direction.lower() == "long" else "Ask"
    order_type = "Market"

    if dry_run:
        log(t("order.dry_run", order_type, side, symbol, usdc_amount, quantity_str))
        return

    # Exécution de l'ordre dans un thread
    response = await asyncio.to_thread(
        account.execute_order,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        reduce_only=False
    )

    executed_quantity = float(response.get("executedQuantity", 0))
    executed_quote_quantity = float(response.get("executedQuoteQuantity", 0))
    status = response.get("status", "UNKNOWN")
    table.append([symbol, side, f"{executed_quantity:.6f} / {quantity_str}",
                  f"{executed_quote_quantity:.2f} / {usdc_amount:.2f}", status])

    print(tabulate(table, headers=headers, tablefmt="grid"))
    return response
