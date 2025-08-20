# dashboard/textdashboard.py
import asyncio
import os
from datetime import datetime
from tabulate import tabulate

from utils.position_utils import get_real_positions
from live.live_engine import handle_live_symbol
from utils.logger import log

# --- GLOBAL TRACKERS ---
trackers = {}  # clé = symbole, valeur = PositionTracker

# --- REFRESH POSITIONS ---
async def refresh_positions():
    """
    Récupère les positions réelles et met à jour les trackers.
    """
    try:
        positions = await get_real_positions()
    except Exception as e:
        log(f"[textdashboard] Erreur get_real_positions: {e}")
        positions = []

    for pos in positions:
        symbol = pos['symbol']
        side = pos['side']
        entry_price = float(pos['entry_price'])
        amount = float(pos['amount'])
        mark_price = float(pos['mark_price'])

        # Met à jour le tracker
        handle_live_symbol(symbol, mark_price, side, entry_price, amount)

# --- DISPLAY DASHBOARD LOOP ---
async def display_dashboard_loop():
    while True:
        await refresh_positions()
        table_data = []
        total_pnl_usd = 0.0

        for symbol, tracker in trackers.items():
            if tracker.direction == "long":
                current_price = tracker.highest_price
            else:
                current_price = tracker.lowest_price

            pnl_percent = tracker.get_unrealized_pnl(current_price)
            pnl_usd = (pnl_percent / 100) * tracker.entry_price * tracker.quantity
            total_pnl_usd += pnl_usd

            duration_sec = (datetime.utcnow() - tracker.entry_time).total_seconds()
            duration_str = f"{int(duration_sec // 3600)}h {(int(duration_sec % 3600) // 60)}m"

            table_data.append([
                symbol,
                tracker.direction,
                f"{tracker.entry_price:.2f}",
                f"{pnl_percent:.2f}%",
                f"${pnl_usd:.2f}",
                tracker.quantity,
                f"${tracker.trailing_stop:.2f}" if tracker.trailing_stop else "N/A",
                duration_str
            ])

        # Affichage
        os.system('clear' if os.name == 'posix' else 'cls')
        print("="*110)
        print(f"🚀 POSITIONS OUVERTES - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"💰 PnL Total: ${total_pnl_usd:.2f}")
        print("="*110)
        print(tabulate(table_data, headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "Amount", "Trailing Stop", "Duration"]))
        print("="*110)

        await asyncio.sleep(1)  # rafraîchissement chaque seconde

# --- LANCEUR DASHBOARD ---
def refresh_dashboard():
    """Lance le dashboard en mode texte"""
    try:
        asyncio.run(display_dashboard_loop())
    except KeyboardInterrupt:
        print("\n[Dashboard] Arrêt manuel du dashboard.")
