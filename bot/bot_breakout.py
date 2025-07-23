import argparse
import time
from backpack_public.public import get_ohlcv
from read.opened_positions import has_open_position
from execute.open_position_usdc import open_position  # c’est la fonction open_position dans ce fichier
from execute.close_position_percent import close_position_percent  # optionnel

BREAKOUT_LOOKBACK = 20
PROFIT_TARGET = 0.01  # 1%

def check_breakout(candles):
    if len(candles) < BREAKOUT_LOOKBACK + 1:
        return None

    prev_candles = candles[-(BREAKOUT_LOOKBACK+1):-1]
    last = candles[-1]

    highs = [float(c["high"]) for c in prev_candles]
    lows = [float(c["low"]) for c in prev_candles]

    max_high = max(highs)
    min_low = min(lows)

    if float(last["close"]) > max_high:
        return "BUY"
    elif float(last["close"]) < min_low:
        return "SELL"
    else:
        return None

def main(raw_symbol, dry_run=False):
    # Adapter le symbole pour l’API klines (sans _PERP)
    if raw_symbol.endswith("_PERP"):
        symbol = raw_symbol[:-5]
    else:
        symbol = raw_symbol

    print(f"\n--- Breakout Bot started for {raw_symbol} ---")
    print(f"Mode : {'dry-run (test)' if dry_run else 'real-run'}")

    limit = BREAKOUT_LOOKBACK + 1
    start_time = int(time.time()) - limit * 60

    candles = get_ohlcv(symbol, interval="1m", limit=limit, startTime=start_time)
    if not candles:
        print("[ERROR] Pas de données OHLCV reçues.")
        return

    signal = check_breakout(candles)
    if not signal:
        print("[INFO] Aucun signal breakout détecté.")
        return

    if has_open_position(raw_symbol):
        print("[INFO] Une position est déjà ouverte sur ce symbole.")
        return

    usdc_amount = 10

    print(f"[SIGNAL] {signal} détecté sur {raw_symbol}")
    if dry_run:
        print(f"[DRY RUN] → {signal} {raw_symbol} pour {usdc_amount} USDC")
    else:
        print(f"[REAL RUN] → {signal} {raw_symbol} pour {usdc_amount} USDC")
        open_position(raw_symbol, usdc_amount, signal.lower())

        entry_price = float(candles[-1]["close"])
        target_price = entry_price * (1 + PROFIT_TARGET) if signal == "BUY" else entry_price * (1 - PROFIT_TARGET)
        print(f"[INFO] Objectif de clôture : {target_price:.4f}")

        while True:
            time.sleep(15)
            latest = get_ohlcv(symbol, "1m", 1)
            if not latest:
                continue
            current_price = float(latest[-1]["close"])
            print(f"[CHECK] Prix actuel : {current_price:.4f}")

            if (signal == "BUY" and current_price >= target_price) or \
               (signal == "SELL" and current_price <= target_price):
                print(f"[EXIT] Fermeture de position : objectif atteint.")
                if not dry_run:
                    # close_position_usdc n’existe pas, on peut utiliser close_position_percent avec 100%
                    close_position_percent(os.environ.get("bpx_bot_public_key"), os.environ.get("bpx_bot_secret_key"), raw_symbol, 100)
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="ex: SOL_USDC_PERP")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Exécute en mode test (sans trader)")
    group.add_argument("--real-run", action="store_true", help="Exécute en mode réel (trading actif)")
    args = parser.parse_args()

    main(args.symbol, dry_run=args.dry_run)
