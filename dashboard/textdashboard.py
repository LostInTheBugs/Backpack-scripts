# dashboard/textdashboard.py
import asyncio
import time
import os
from datetime import datetime
from tabulate import tabulate

from utils.logger import log
from utils.position_tracker import PositionTracker
from live.live_engine import trackers  # on suppose que live_engine garde un dict {symbol: tracker}

class Dashboard:
    async def render_loop(self):
        while True:
            try:
                await asyncio.sleep(2)
                os.system("clear" if os.name == "posix" else "cls")

                print("=" * 110)
                print(f"🚀 DASHBOARD - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
                print("=" * 110)

                table_data = []
                total_pnl_usd = 0.0

                for symbol, tracker in trackers.items():
                    # ⚡ Utiliser la méthode centrale
                    status = tracker.get_status(current_price=tracker.highest_price if tracker.direction == "long" else tracker.lowest_price)

                    if not status:
                        continue

                    pnl_pct = status["pnl_pct"]
                    entry_price = status["entry_price"]
                    current_price = status["current_price"]
                    trailing_stop = status["trailing_stop"]

                    # Approx PnL $ (si quantité dispo)
                    pnl_usd = (pnl_pct / 100) * entry_price * tracker.quantity
                    total_pnl_usd += pnl_usd

                    table_data.append([
                        symbol,
                        status["direction"],
                        f"{entry_price:.4f}",
                        f"{current_price:.4f}",
                        f"{pnl_pct:.2f}%",
                        f"${pnl_usd:.2f}",
                        tracker.quantity,
                        f"{trailing_stop:.4f}" if trailing_stop else "N/A",
                        "❌" if status["should_close"] else ""
                    ])

                if table_data:
                    print(tabulate(
                        table_data,
                        headers=["Symbol", "Side", "Entry", "Current", "PnL%", "PnL$", "Amount", "Trailing Stop", "Exit?"],
                        tablefmt="fancy_grid"
                    ))
                    print(f"\n💰 Total PnL: ${total_pnl_usd:.2f}")
                else:
                    print("No open positions.")

            except Exception as e:
                log(f"[ERROR] Dashboard loop: {e}", level="ERROR")
                await asyncio.sleep(5)

def main():
    try:
        asyncio.run(Dashboard().render_loop())
    except KeyboardInterrupt:
        log("Dashboard stopped by user.")

if __name__ == "__main__":
    main()
