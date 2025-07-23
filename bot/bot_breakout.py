import time
import argparse
from list.breakout_signal import breakout_signal
from execute.open_position_usdc import open_position
from execute.close_position import close_position
from backpack_public.public import get_open_position, get_mark_price

AMOUNT_USDC = 10  # Montant à engager par position
TARGET_PNL = 0.002  # 0.2% profit cible

def check_and_trade(symbol, real_run):
    signal = breakout_signal(symbol)

    position = get_open_position(symbol)
    mark_price = get_mark_price(symbol)

    if position:
        entry = float(position["entryPrice"])
        direction = position["side"]
        pnl_pct = (mark_price - entry) / entry if direction == "long" else (entry - mark_price) / entry

        if pnl_pct >= TARGET_PNL:
            print(f"[INFO] PnL {pnl_pct*100:.2f}% atteint. Fermeture position.")
            if real_run:
                close_position(symbol)
            else:
                print("[DRY-RUN] Fermeture simulée.")
        else:
            print(f"[INFO] Position ouverte (side: {direction}) - PnL: {pnl_pct*100:.3f}%")
    else:
        if signal in ["BUY", "SELL"]:
            print(f"[INFO] Signal détecté : {signal}")
            if real_run:
                direction = "long" if signal == "BUY" else "short"
                open_position(symbol, AMOUNT_USDC, direction)
            else:
                print(f"[DRY-RUN] Ouverture position {signal}")
        else:
            print("[INFO] Aucun signal breakout détecté.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", type=str)
    parser.add_argument("--real-run", action="store_true")
    args = parser.parse_args()

    print(f"\n--- Breakout Bot started for {args.symbol} ---")
    print(f"Mode : {'real-run' if args.real_run else 'dry-run'}")

    try:
        while True:
            check_and_trade(args.symbol, args.real_run)
            time.sleep(1)
    except KeyboardInterrupt:
        print("⛔️ Bot interrompu par l'utilisateur.")
