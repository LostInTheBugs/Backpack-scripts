import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import time
from execute.open_position_usdc import open_position
from list.orderbook_signal import get_orderbook_signal  # Tu peux remplacer par la fonction intégrée ci-dessous si besoin

from bpx.public import Public

public = Public()

def get_orderbook_signal(symbol: str, volume_threshold=50, sensitivity=1.1):
    """
    Récupère l'ordre du carnet et renvoie un signal 'BUY', 'SELL' ou 'HOLD'
    basé sur l'asymétrie des volumes bid/ask.
    - volume_threshold : volume total minimum pour considérer un signal
    - sensitivity : ratio bid/ask pour déclencher BUY ou SELL
    """
    # Récupération du carnet de commandes (depth)
    orderbook = public.get_orderbook(symbol, depth=10)
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    # Calcul du volume cumulé
    bid_volume = sum(float(bid[1]) for bid in bids)
    ask_volume = sum(float(ask[1]) for ask in asks)

    print(f"📊 Bids volume: {bid_volume:.2f} | Asks volume: {ask_volume:.2f}")

    total_volume = bid_volume + ask_volume
    if total_volume < volume_threshold:
        print(f"⚠️ Volume total trop faible ({total_volume:.2f}), pas de signal")
        return "HOLD"

    if bid_volume > ask_volume * sensitivity:
        return "BUY"
    elif ask_volume > bid_volume * sensitivity:
        return "SELL"
    else:
        return "HOLD"

async def run_bot(symbol, usdc_amount, interval, leverage):
    print(f"🔄 Starting bot for {symbol} with {usdc_amount} USDC | Interval: {interval}s | Leverage: x{leverage}")

    while True:
        try:
            signal = get_orderbook_signal(symbol)
            if signal == "BUY":
                print("📈 Signal: BUY")
                open_position(symbol, usdc_amount * leverage, "long")
            elif signal == "SELL":
                print("📉 Signal: SELL")
                open_position(symbol, usdc_amount * leverage, "short")
            else:
                print(f"⏸️ No signal for {symbol}")

            await asyncio.sleep(interval)

        except Exception as e:
            print(f"⚠️ Error in bot loop: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 bot_orderbook.py <SYMBOL> <USDC_AMOUNT> [INTERVAL] [LEVERAGE]")
        sys.exit(1)

    symbol = sys.argv[1]
    try:
        usdc_amount = float(sys.argv[2])
    except ValueError:
        print("Invalid USDC amount.")
        sys.exit(1)

    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    leverage = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    asyncio.run(run_bot(symbol, usdc_amount, interval, leverage))
