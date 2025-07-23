import time
import argparse
from datetime import datetime

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position import close_position
from backpack_public.public import get_ohlcv

POSITION_AMOUNT_USDC = 20  # à adapter selon ta stratégie
PNL_THRESHOLD_CLOSE = 0.002  # 0.2%

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
                else:
                    log(f"[{symbol}] [Dry-run] Ouverture de position {signal.lower()} ignorée.")
        else:
            log(f"[{symbol}] 🕵️ Aucun signal breakout détecté.")

        if has_open_position(symbol):
            pnl = get_position_pnl(symbol)
            pnl_percent = pnl / POSITION_AMOUNT_USDC
            if pnl_percent >= PNL_THRESHOLD_CLOSE:
                log(f"[{symbol}] 🎯 PnL {pnl:.2f} USDC atteint ({pnl_percent*100:.2f}%). Fermeture de position.")
                if real_run:
                    close_position(symbol)
                else:
                    log(f"[{symbol}] [Dry-run] Fermeture de position ignorée.")
            else:
                log(f"[{symbol}] 📊 PnL actuel : {pnl:.4f} USDC ({pnl_percent*100:.2f}%)")

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
    parser = argparse.ArgumentParser(description="Breakout bot for Backpack Exchange")
    parser.add_argument("symbols", type=str, help="Liste des symboles séparés par des virgules (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    main(symbols, real_run=args.real_run)
