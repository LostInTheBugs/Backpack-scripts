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

def open_position(symbol: str, usdc_amount: float, direction: str, tp_percent: float = None, sl_percent: float = None):
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    public = Public()

    # Vérifier s'il y a déjà une position ouverte sur le symbole
    positions = account.get_open_positions()
    existing_position = next((p for p in positions if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0), None)

    # Récupérer la liste des marchés
    markets = public.get_markets()
    if not isinstance(markets, list):
        print("Failed to retrieve market list.")
        return

    if not any(m.get("symbol") == symbol for m in markets):
        print(f"Symbol '{symbol}' not found in market list.")
        return

    # Récupérer le ticker (dernier prix)
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
        # Position existante : on ajoute uniquement de la quantité sans poser TP/SL
        print(f"Position already open on {symbol} with qty {existing_position.get('quantity')}. Adding {quantity} units without modifying TP/SL.")

        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            reduce_only=False
        )

        print("Added to position response:", response)
        return

    # Sinon nouvelle position, on ouvre + pose TP/SL si fournis
    print(f"Submitting {order_type} {side} order on {symbol} using {usdc_amount} USDC ≈ {quantity} units")

    response = account.execute_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        reduce_only=False
    )

    executedQuantity = float(response.get("executedQuantity", quantity))
    executedQuoteQuantity = float(response.get("executedQuoteQuantity", usdc_amount))
    status = response.get("status", "UNKNOWN")
    avg_price = float(response.get("avgPrice", mark_price))

    def price_tp_sl(price, tp_p, sl_p, side):
        if tp_p is None and sl_p is None:
            return None, None
        if side.lower() == "bid":  # long
            tp_price = price * (1 + tp_p / 100) if tp_p is not None else None
            sl_price = price * (1 - sl_p / 100) if sl_p is not None else None
        else:  # short
            tp_price = price * (1 - tp_p / 100) if tp_p is not None else None
            sl_price = price * (1 + sl_p / 100) if sl_p is not None else None
        return tp_price, sl_price

    tp_price, sl_price = price_tp_sl(avg_price, tp_percent, sl_percent, side)

    print(f"Order executed: {executedQuantity} units at avg price {avg_price}")
    if tp_price:
        print(f"Take Profit price set at: {tp_price:.{step_size_decimals}f}")
    if sl_price:
        print(f"Stop Loss price set at: {sl_price:.{step_size_decimals}f}")

    if tp_price:
        tp_response = account.execute_order(
            symbol=symbol,
            side="Ask" if side == "Bid" else "Bid",
            order_type="Limit",
            quantity=executedQuantity,
            price=round(tp_price, step_size_decimals),
            reduce_only=True
        )
        print("Take Profit order response:", tp_response)

    if sl_price:
        try:
            sl_response = account.execute_order(
                symbol=symbol,
                side="Ask" if side == "Bid" else "Bid",
                order_type="StopMarket",
                quantity=executedQuantity,
                stop_price=round(sl_price, step_size_decimals),
                reduce_only=True
            )
            print("Stop Loss order response:", sl_response)
        except TypeError:
            print("Stop loss order not placed: 'stop_price' param not supported by execute_order.")

    table = [[
        symbol,
        side,
        f"{executedQuantity} / {quantity}",
        f"{executedQuoteQuantity} / {usdc_amount}",
        status,
    ]]

    print(tabulate(table, headers=["Symbol", "Order type", "Quantity Executed/Ordered", "Amount Executed/Ordered", "Status"], tablefmt="grid"))

if __name__ == "__main__":
    argc = len(sys.argv)
    if argc < 4 or argc > 6:
        print("Usage: python open_position_usdc.py <SYMBOL> <USDC_AMOUNT> <DIRECTION> [TP_PERCENT] [SL_PERCENT]")
        print("Example: python open_position_usdc.py SOL_USDC_PERP 25 long 3 1")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        usdc_amount = float(sys.argv[2])
    except ValueError:
        print("USDC amount must be a number.")
        sys.exit(1)

    direction = sys.argv[3]

    tp_percent = None
    sl_percent = None
    if argc >= 5:
        try:
            tp_percent = float(sys.argv[4])
        except ValueError:
            print("TP percent must be a number.")
            sys.exit(1)
    if argc == 6:
        try:
            sl_percent = float(sys.argv[5])
        except ValueError:
            print("SL percent must be a number.")
            sys.exit(1)

    open_position(symbol, usdc_amount, direction, tp_percent, sl_percent)
