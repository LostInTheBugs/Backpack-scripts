import argparse
import time
from backpack_public.public import get_ohlcv
from read.opened_positions import has_open_position
from execute.open_position_usdc import open_position
from execute.close_position_usdc import close_position_usdc  # optionnel

BREAKOUT_LOOKBACK = 20
PROFIT_TARGET = 0.01

def check_breakout(candles):
    if len(candles) < BREAKOUT_LOOKBACK + 1:
        return None

    prev_candles = candles[-(BREAKOUT_LOOKBACK+1):-1]
    last = candles[-1]

    highs = [c["high"] for c in prev_candles]
    lows = [c["low"] for c in prev_candles]

    max_high = max(highs)
    min_low = min(lows)

    if last["close"] > max_high:
        return "BUY"
    elif last["close"] < min_low:
        return "SELL"
    else:
        return None

def main(symbol, dry_run=False):
    print(f"\n--- Breakout Bot started for {symbol} ---")
    print(f"Mode : {'dry-run (test)' if dry_run else 'real-run'}")

    candles = get_ohlcv(symbol, interval="1m", limit=BREAKOUT_LOOKBACK + 1)
    if not candles:
        print("[ERROR] Pas de données OHLCV reçues.")
        return

    signal = check_breakout(candles)
    if not signal:
        print("[INFO] Aucun signal breakout détecté.")
        return

    if has_open_position(symbol):
        print("[INFO] Une position est déjà ouverte sur ce symbole.")
        return

    usdc_amount = 10

    print(f"[SIGNAL] {signal} détecté sur {symbol}")
    if dry_run:
        print(f"[DRY RUN] → {signal} {symbol} pour {usdc_amount} USDC")
    else:
        print(f"[REAL RUN] → {signal} {symbol} pour {usdc_amount} USDC")
        open_position_usdc(symbol, usdc_amount, signal.lower())

        entry_price = candles[-1]["close"]
        target_price = entry_price * (1 + PROFIT_TARGET) if signal == "BUY" else entry_price * (1 - PROFIT_TARGET)
        print(f"[INFO] Objectif de clôture : {target_price:.4f}")

        while True:
            time.sleep(15)
            latest = get_ohlcv(symbol, "1m", 1)
            if not latest:
                continue
            current_price = latest[-1]["close"]
            print(f"[CHECK] Prix actuel : {current_price:.4f}")

            if (signal == "BUY" and current_price >= target_price) or \
               (signal == "SELL" and current_price <= target_price):
                print(f"[EXIT] Fermeture de position : objectif atteint.")
                if not dry_run:
                    close_position_usdc(symbol)
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="ex: BTC-USDC")
    parser.add_argument("--dry-run", action="store_true", help="Exécute en mode test (sans trader)")
    parser.add_argument("--real-run", action="store_true", help="Exécute en mode réel (trading actif)")
    args = parser.parse_args()

    if not args.dry_run and not args.real_run:
        print("❌ Veuillez préciser --dry-run ou --real-run")
    else:
        main(args.symbol, dry_run=args.dry_run)
