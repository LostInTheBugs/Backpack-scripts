import time
import argparse
import os
from datetime import datetime

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.public import get_ohlcv

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20              # Montant d'ouverture de position
PNL_THRESHOLD_CLOSE = 0.002            # Take profit à +0.2%
TRAILING_STOP_PERCENT = 0.002          # Stop loss suiveur à -0.2%

# Pour stocker le PnL maximum observé par symbole
max_pnl_percent_seen = {}

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def handle_symbol(symbol: str, real_run: bool):
    try:
        ohlcv = get_ohlcv(symbol, interval="1m", limit=100)
        signal = breakout_signal(ohlcv)
        log(f"[{symbol}] Signal brut retourné: {signal} ({type(signal)})")

        if signal in ["BUY", "SELL"]:
            if has_open_position(symbol):
                log(f"[{symbol}] 🔄 Une position est déjà ouverte.")
            else:
                log(f"[{symbol}] 📈 Signal détecté : {signal}. Ouverture d'une position.")
                if real_run:
                    direction = "long" if signal.lower() == "buy" else "short"
                    open_position(symbol, POSITION_AMOUNT_USDC, direction)
                    max_pnl_percent_seen[symbol] = 0.0  # Initialiser après ouverture
                else:
                    log(f"[{symbol}] [Dry-run] Ouverture de position {signal.lower()} ignorée.")
        else:
            log(f"[{symbol}] 🕵️ Aucun signal breakout détecté.")

        if has_open_position(symbol):
            pnl = get_position_pnl(symbol)
            pnl_percent = pnl / POSITION_AMOUNT_USDC

            # Suivi du PnL max
            prev_max = max_pnl_percent_seen.get(symbol, 0.0)
            max_pnl_percent_seen[symbol] = max(prev_max, pnl_percent)

            log(f"[{symbol}] 📊 PnL actuel : {pnl:.4f} USDC ({pnl_percent*100:.2f}%) | PnL max : {max_pnl_percent_seen[symbol]*100:.2f}%")

            # 🔒 Take Profit
            if pnl_percent >= PNL_THRESHOLD_CLOSE:
                log(f"[{symbol}] 🎯 Take Profit atteint. Fermeture de position.")
                if real_run:
                    close_position_percent(public_key, secret_key, symbol, 100)
                    max_pnl_percent_seen[symbol] = 0.0
                else:
                    log(f"[{symbol}] [Dry-run] Fermeture de position ignorée.")

            # 🛡️ Stop Loss Suiveur
            elif max_pnl_percent_seen[symbol] - pnl_percent >= TRAILING_STOP_PERCENT:
                log(f"[{symbol}] 🛑 Stop Loss suiveur déclenché ({pnl_percent*100:.2f}% < max {max_pnl_percent_seen[symbol]*100:.2f}%)")
                if real_run:
                    close_position_percent(public_key, secret_key, symbol, 100)
                    max_pnl_percent_seen[symbol] = 0.0
                else:
                    log(f"[{symbol}] [Dry-run] Fermeture via Stop Loss suiveur ignorée.")

    except Exception as e:
        log(f"[{symbol}] ❌ Erreur : {e}")

def main(symbols: list, real_run: bool):
    log(f"--- Breakout Bot started for symbols: {', '.join(symbols)} ---")
    log(f"Mode : {'real-run' if real_run else 'dry-run'}")

    while True:
        for symbol in symbols:
            handle_symbol(symbol, real_run)
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout bot with trailing stop for Backpack Exchange")
    parser.add_argument("symbols", type=str, help="Liste des symboles séparés par des virgules (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    main(symbols, real_run=args.real_run)
