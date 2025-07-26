#!/usr/bin/env python3
from bpx.account import Account
from bpx.public import Public
from tabulate import tabulate
import os
import sys

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_step_size_decimals(market_info):
    step_size = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "1")
    if '.' in step_size:
        return len(step_size.split(".")[1].rstrip("0"))
    return 0

def open_position_perp(symbol: str, usdc_amount: float, direction: str, leverage: float, tp_percent: float = None, sl_percent: float = None):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    # 🔧 Affichage manuel du levier
    print(f"⚙️ Requested leverage: x{leverage} — configure manually on Backpack UI if needed")

    # Vérifier position ouverte existante
    positions = account.get_open_positions()
    existing_position = next((p for p in positions if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0), None)

    markets = public.get_markets()
    if not isinstance(markets, list):
        print("Failed to retrieve market list.")
        return

    if not any(m.get("symbol") == symbol for m in markets):
        print(f"Symbol '{symbol}' not found in market list.")
        return

    ticker = public.get_ticker(symbol)
    if not isinstance(ticker, dict):
        print("Failed to retrieve ticker data.")
        return

    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price == 0:
        print("Invalid mark price from ticker.")
        return

    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(f"Symbol '{symbol}' not found.")
        return 

    step_size_decimals = get_step_size_decimals(market_info)
    quantity = round(usdc_amount / mark_price, step_size_decimals)

    side = "Bid" if direction.lower() == "long" else "Ask"
    order_type = "Market"

    if existing_position:
        print(f"⚠️ Position already open on {symbol} with qty {existing_position.get('quantity')}. Adding {quantity} units (no TP/SL).")
        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            reduce_only=False
        )
        print("Added to position response:", response)
        return

    print(f"📤 Submitting {order_type} {side} order on {symbol} with {usdc_amount} USDC ≈ {quantity} units")

    tp_price = sl_price = None
    if tp_percent or sl_percent:
        if side.lower() == "bid":  # long
            tp_price = mark_price * (1 + tp_percent / 100) if tp_percent else None
            sl_price = mark_price * (1 - sl_percent / 100) if sl_percent else None
        else:  # short
            tp_price = mark_price * (1 - tp_percent / 100) if tp_percent else None
            sl_price = mark_price * (1 + sl_percent / 100) if sl_percent else None

        if tp_price:
            print(f"🎯 TP @ {round(tp_price, step_size_decimals)}")
        if sl_price:
            print(f"🛑 SL @ {round(sl_price, step_size_decimals)}")

    try:
        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=str(quantity),
            reduce_only=False,
            take_profit_trigger_price=str(round(tp_price, step_size_decimals)) if tp_price else None,
            take_profit_limit_price=str(round(tp_price, step_size_decimals)) if tp_price else None,
            stop_loss_trigger_price=str(round(sl_price, step_size_decimals)) if sl_price else None,
            stop_loss_limit_price=str(round(sl_price, step_size_decimals)) if sl_price else None,
            triggered_by="LastPrice"
        )
    except TypeError as e:
        print(f"❌ Failed to execute order with TP/SL: {e}")
        return

    executedQuantity = float(response.get("executedQuantity", quantity))
    executedQuoteQuantity = float(response.get("executedQuoteQuantity", usdc_amount))
    status = response.get("status", "UNKNOWN")
    avg_price = float(response.get("avgPrice", mark_price))

    print(f"✅ Order executed: {executedQuantity} units at avg price {avg_price}")

    table = [[
        symbol,
        side,
        f"{executedQuantity} / {quantity}",
        f"{executedQuoteQuantity} / {usdc_amount}",
        status,
    ]]

    print(tabulate(table, headers=["Symbol", "Side", "Qty Ex/Ord", "USDC Ex/Ord", "Status"], tablefmt="grid"))

if __name__ == "__main__":
    argc = len(sys.argv)
    if argc < 5 or argc > 7:
        print("Usage: python open_position_perp_tpsl.py <SYMBOL> <USDC_AMOUNT> <DIRECTION> <LEVERAGE> [TP_PERCENT] [SL_PERCENT]")
        print("Example: python open_position_perp_tpsl.py SOL_USDC_PERP 25 long 10 3 1")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        usdc_amount = float(sys.argv[2])
    except ValueError:
        print("USDC amount must be a number.")
        sys.exit(1)

    direction = sys.argv[3]

    try:
        leverage = float(sys.argv[4])
    except ValueError:
        print("Leverage must be a number.")
        sys.exit(1)

    tp_percent = None
    sl_percent = None
    if argc >= 6:
        try:
            tp_percent = float(sys.argv[5])
        except ValueError:
            print("TP percent must be a number.")
            sys.exit(1)
    if argc == 7:
        try:
            sl_percent = float(sys.argv[6])
        except ValueError:
            print("SL percent must be a number.")
            sys.exit(1)

    open_position_perp(symbol, usdc_amount, direction, leverage, tp_percent, sl_percent)
