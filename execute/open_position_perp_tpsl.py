#!/usr/bin/env python3
import os
import sys
from tabulate import tabulate
from bpx.account import Account
from bpx.public import Public

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_step_size_decimals(market_info):
    step_size = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "1")
    return len(step_size.split(".")[1].rstrip("0")) if '.' in step_size else 0

def open_position_perp(symbol: str, usdc_amount: float, direction: str, leverage: float, tp_percent: float = None, sl_percent: float = None):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    print(f"⚙️ Requested leverage: x{leverage} — configure manually on Backpack UI if needed")

    positions = account.get_open_positions()
    existing_position = next((p for p in positions if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0), None)

    markets = public.get_markets()
    if not isinstance(markets, list):
        print("Failed to retrieve market list.")
        return

    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(f"Symbol '{symbol}' not found.")
        return

    step_size_decimals = get_step_size_decimals(market_info)

    ticker = public.get_ticker(symbol)
    if not isinstance(ticker, dict):
        print("Failed to retrieve ticker.")
        return
    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price <= 0:
        print("Invalid mark price.")
        return

    quantity = round(usdc_amount / mark_price, step_size_decimals)
    side = "Bid" if direction.lower() == "long" else "Ask"

    def compute_tp_sl(price):
        if side.lower() == "bid":  # long
            tp_price = price * (1 + (tp_percent or 0) / 100)
            sl_price = price * (1 - (sl_percent or 0) / 100)
        else:  # short
            tp_price = price * (1 - (tp_percent or 0) / 100)
            sl_price = price * (1 + (sl_percent or 0) / 100)
        return tp_price, sl_price

    tp_price, sl_price = compute_tp_sl(mark_price)

    if existing_position:
        print(f"🔁 Position already open on {symbol}. Adding {quantity} units.")
        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type="Market",
            quantity=quantity,
            reduce_only=False
        )
        print("Response:", response)
        return

    print(f"📤 Submitting Market {side} order on {symbol} with {usdc_amount} USDC ≈ {quantity} units")

    kwargs = dict(
        symbol=symbol,
        side=side,
        order_type="Market",
        quantity=quantity,
        reduce_only=False
    )

    if tp_percent:
        kwargs["takeProfitTriggerPrice"] = f"{tp_price:.{step_size_decimals}f}"
        kwargs["takeProfitLimitPrice"] = f"{tp_price:.{step_size_decimals}f}"
    if sl_percent:
        kwargs["stopLossTriggerPrice"] = f"{sl_price:.{step_size_decimals}f}"
        kwargs["stopLossLimitPrice"] = f"{sl_price:.{step_size_decimals}f}"

    response = account.execute_order(**kwargs)

    executed_qty = float(response.get("executedQuantity", 0))
    executed_amt = float(response.get("executedQuoteQuantity", 0))
    avg_price = float(response.get("avgPrice", mark_price))
    status = response.get("status", "UNKNOWN")

    print(f"✅ Order executed: {executed_qty} units at avg price {avg_price}")
    if tp_percent:
        print(f"🎯 TP @ {tp_price:.{step_size_decimals}f}")
    if sl_percent:
        print(f"🛑 SL @ {sl_price:.{step_size_decimals}f}")

    table = [[
        symbol,
        side,
        f"{executed_qty} / {quantity}",
        f"{executed_amt:.4f} / {usdc_amount:.4f}",
        status,
    ]]

    print(tabulate(table, headers=["Symbol", "Side", "Qty Ex/Ord", "USDC Ex/Ord", "Status"], tablefmt="grid"))

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python open_position_perp.py <SYMBOL> <USDC_AMOUNT> <DIRECTION> <LEVERAGE> [TP_PERCENT] [SL_PERCENT]")
        sys.exit(1)

    symbol = sys.argv[1]
    usdc_amount = float(sys.argv[2])
    direction = sys.argv[3]
    leverage = float(sys.argv[4])
    tp_percent = float(sys.argv[5]) if len(sys.argv) > 5 else None
    sl_percent = float(sys.argv[6]) if len(sys.argv) > 6 else None

    open_position_perp(symbol, usdc_amount, direction, leverage, tp_percent, sl_percent)
