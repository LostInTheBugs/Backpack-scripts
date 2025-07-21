import time
import sys
import argparse
from datetime import datetime
import os

from list.opened_positions import get_open_positions
from execute.close_position_percent import close_position_percent
from execute.open_position_usdc import open_position_usdc
from public.public import get_ohlcv

LOOKBACK = 20
TIMEFRAME = "1m"
AMOUNT_USDC = 25
PROFIT_TARGET = 0.01  # 1%

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def detect_breakout(data):
    highs = [c["high"] for c in data[:-1]]
    lows = [c["low"] for c in data[:-1]]
    close = data[-1]["close"]

    if close > max(highs):
        return "BUY"
    elif close < min(lows):
        return "SELL"
    return "HOLD"

def already_has_position(symbol, positions):
    for pos in positions:
        if pos["symbol"] == symbol and float(pos.get("netQuantity", 0)) != 0:
            return True
    return False

def check_and_close_position(symbol, positions, dry_run):
    for pos in positions:
        if pos["symbol"] != symbol:
            continue

        entry = float(pos.get("entryPrice", 0))
        current = float(pos.get("currentPrice", 0))
        net_qty = float(pos.get("netQuantity", 0))

        if net_qty == 0 or entry == 0:
            continue

        side = "long" if net_qty > 0 else "short"
        gain = (current - entry) / entry if side == "long" else (entry - current) / entry

        if gain >= PROFIT_TARGET:
            print(f"[{datetime.utcnow()}] 🎯 Fermeture de position {side} sur {symbol} (+1%)")
            if not dry_run:
                close_position_percent(public_key, secret_key, symbol, 100)
            else:
                print("⚠️ [dry-run] → Position NON fermée.")

def main(symbol: str, dry_run: bool):
    print(f"--- Breakout Bot started for {symbol} ---")
    print(f"Mode : {'dry-run (test)' if dry_run else 'real-run (LIVE)'}")

    while True:
        try:
            ohlcv = get_ohlcv(symbol, TIMEFRAME, limit=LOOKBACK)
            if not ohlcv or len(ohlcv) < LOOKBACK:
                print("Pas assez de données OHLCV.")
                time.sleep(10)
                continue

            positions = get_open_positions(public_key, secret_key)

            # Fermeture auto si +1%
            check_and_close_position(symbol, positions, dry_run)

            # Sauter si position déjà ouverte
            if already_has_position(symbol, positions):
                print(f"[{datetime.utcnow()}] Une position existe déjà pour {symbol}")
                time.sleep(60)
                continue

            # Détection breakout
            signal = detect_breakout(ohlcv)
            print(f"[{datetime.utcnow()}] Signal : {signal}")

            if signal == "BUY":
                if dry_run:
                    print(f"[dry-run] → OUVERTURE LONG {symbol} pour {AMOUNT_USDC} USDC")
                else:
                    open_position_usdc(symbol, "long", AMOUNT_USDC)
            elif signal == "SELL":
                if dry_run:
                    print(f"[dry-run] → OUVERTURE SHORT {symbol} pour {AMOUNT_USDC} USDC")
                else:
                    open_position_usdc(symbol, "short", AMOUNT_USDC)

        except Exception as e:
            print(f"❌ Erreur : {e}")

        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="Ex: BTC-USDC ou SOL_USDC_PERP")
    parser.add_argument("--dry-run", action="store_true", help="Mode test (aucun ordre réel)")
    parser.add_argument("--real-run", action="store_true", help="Mode réel (ordres exécutés)")

    args = parser.parse_args()

    if not args.dry_run and not args.real_run:
        print("❌ Spécifie --dry-run ou --real-run pour lancer le bot.")
        sys.exit(1)

    main(args.symbol, dry_run=args.dry_run)
