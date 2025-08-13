import os
from decimal import Decimal
from tabulate import tabulate
import asyncio

from bpx.account import Account, OrderTypeEnum
from bpx.public import Public

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_step_size_decimals(market_info):
    step_size = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "1")
    return len(step_size.split(".")[1].rstrip("0")) if '.' in step_size else 0

async def get_open_positions():
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = await asyncio.to_thread(account.get_open_positions)
    if not isinstance(positions, list):
        raise ValueError("Could not retrieve open positions.")
    return positions

async def close_position_percent(symbol: str, percent: float):
    if percent <= 0 or percent > 100:
        raise ValueError("Invalid percentage. Must be between 0 and 100.")

    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    markets = await asyncio.to_thread(public.get_markets)
    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        raise ValueError(f"Market info for symbol '{symbol}' not found")

    step_size_decimals = get_step_size_decimals(market_info)

    positions = await get_open_positions()

    headers = ["Symbol", "Side", "Order type", "Quantity Executed/Ordered", "Amount Executed/Ordered", "Status"]
    table = []

    for position in positions:
        if position.get("symbol") != symbol:
            continue

        net_qty = float(position.get("netQuantity", 0))
        if net_qty == 0:
            raise ValueError(f"No open position found for symbol '{symbol}'.")

        side = "Ask" if net_qty > 0 else "Bid"
        qty_to_close = round(abs(net_qty) * (percent / 100), step_size_decimals)

        response = await asyncio.to_thread(
            account.execute_order,
            symbol=symbol,
            side=side,
            order_type=OrderTypeEnum.MARKET,
            quantity=f"{qty_to_close:.{step_size_decimals}f}",
            reduce_only=True
        )

        executed_quantity = response.get("executedQuantity", "N/A")
        quantity_ordered = response.get("quantity", f"{qty_to_close:.{step_size_decimals}f}")
        executed_quote_qty = response.get("executedQuoteQuantity", "N/A")
        quote_quantity = response.get("quoteQuantity", "N/A")
        status = response.get("status", "N/A")
        order_type = response.get("orderType", "Market")

        table.append([
            symbol, side, order_type, f"{executed_quantity} / {quantity_ordered}",
            f"{executed_quote_qty} / {quote_quantity}", status
        ])

        print(tabulate(table, headers=headers, tablefmt="grid"))
        return response

    raise ValueError(f"No position found for symbol '{symbol}'.")
