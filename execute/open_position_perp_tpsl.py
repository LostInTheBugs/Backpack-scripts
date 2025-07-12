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

    print(f"⚙️ Requested leverage: x{leverage} — configure manually on Backpack UI if needed")

    # Vérifier position ouverte existante
    positions = account.get_open_positions()
    existing_position = next((p for p in positions if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0), None)

    # Récupérer les infos de marché
    markets = public.get_markets()
    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(f"Symbol '{symbol}' not found in market list.")
        return

    ticker = public.get_ticker(symbol)
    mark_price = float(ticker.get("lastPrice", "0"))
    if mark_price == 0:
        print("Invalid mark price.")
        return

    step_size_decimals = get_step_size_decimals(market_info)
    quantity = round(usdc_amount / mark_price, step_size_decimals)

    side = "Bid" if direction.lower() == "long" else "Ask"
    order_type = "Market"

    if existing_position:
        print(f"📌 Existing position detected. Adding {quantity} units.")
        response = account.execute_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            reduce_only=False
        )
        print("Added to position:", response)
        return

    print(f"📤 Submitting {order_type} {side} order on {symbol} with {usdc_amount} USDC ≈ {quantity} units")

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

    def compute_tp_sl(price, tp_p, sl_p, side):
        if side.lower() == "bid":
            tp = price * (1 + (tp_p or 0) / 100)
            sl = price * (1 - (sl_p or 0) / 100)
        else:
            tp = price * (1 - (tp_p or 0) / 100)
            sl = price * (1 + (sl_p or 0) / 100)
        return round(tp, step_size_decimals), round(sl, step_size_decimals)

    tp_price, sl_price = compute_tp_sl(avg_price, tp_percent, sl_percent, side)

    print(f"✅ Order executed: {executedQuantity} units at avg price {avg_price}")
    if tp_percent:
        print(f"🎯 TP @ {tp_price}")
    if sl_percent:
        print(f"🛑 SL @ {sl_price} (not applied)")

    # Placer le TP uniquement (SL non supporté)
    if tp_percent:
        tp_response = account.execute_order(
            symbol=symbol,
            side="Ask" if side == "Bid" else "Bid",
            order_type="Limit",
            quantity=executedQuantity,
            price=tp_price,
            reduce_only=True
        )
        print("📈 TP order response:", tp_response)

    # ⚠️ SL non pris en charge, avertir
    if sl_percent:
        print("⚠️ SL not set: 'StopMarket' likely not supported by this SDK")

    table = [[
        symbol,
        side,
        f"{executedQuantity} / {quantity}",
        f"{executedQuoteQuantity} / {usdc_amount}",
        status,
    ]]
    print(tabulate(table, headers=["Symbol", "Side", "Qty Ex/Ord", "USDC Ex/Ord", "Status"], tablefmt="grid"))

# Entrée script
if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python open_position_perp.py <SYMBOL> <USDC_AMOUNT> <DIRECTION> <LEVERAGE> [TP] [SL]")
        sys.exit(1)

    symbol = sys.argv[1]
    usdc_amount = float(sys.argv[2])
    direction = sys.argv[3]
    leverage = float(sys.argv[4])
    tp_percent = float(sys.argv[5]) if len(sys.argv) > 5 else None
    sl_percent = float(sys.argv[6]) if len(sys.argv) > 6 else None

    open_position_perp(symbol, usdc_amount, direction, leverage, tp_percent, sl_percent)
