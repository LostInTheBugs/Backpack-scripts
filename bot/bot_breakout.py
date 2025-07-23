import time
import argparse
from datetime import datetime

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position import close_position
from backpack_public.public import get_ohlcv

SYMBOL = None
POSITION_AMOUNT_USDC = 20  # à adapter selon ta stratégie

PNL_THRESHOLD_CLOSE = 0.002  # 0.2% en décimal (0.2 / 100)

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def main(symbol: str, real_run: bool):
    global SYMBOL
    SYMBOL = symbol
    log(f"--- Breakout Bot started for {symbol} ---")
    log(f"Mode : {'real-run' if real_run else 'dry-run'}")

    while True:
        try:
            ohlcv = get_ohlcv(symbol, interval_sec="1m", limit=100)
            signal = breakout_signal(symbol)
            log(f"[DEBUG] Signal brut retourné: {signal} ({type(signal)})")
            if signal in ["BUY", "SELL"]:
                if has_open_position(symbol):
                    log(f"🔄 Une position est déjà ouverte sur {symbol}.")
                else:
                    log(f"📈 Signal détecté : {signal}. Ouverture d'une position.")
                    if real_run:
                        open_position(symbol, signal.lower(), POSITION_AMOUNT_USDC)
                    else:
                        log(f"[Dry-run] Ouverture de position {signal.lower()} ignorée.")
            else:
                log("🕵️ Aucun signal breakout détecté.")

            if has_open_position(symbol):
                pnl = get_position_pnl(symbol)
                pnl_percent = pnl / POSITION_AMOUNT_USDC
                if pnl_percent >= PNL_THRESHOLD_CLOSE:
                    log(f"🎯 PnL {pnl:.2f} USDC atteint ({pnl_percent*100:.2f}%). Fermeture de position.")
                    if real_run:
                        close_position(symbol)
                    else:
                        log("[Dry-run] Fermeture de position ignorée.")
                else:
                    log(f"📊 PnL actuel : {pnl:.4f} USDC ({pnl_percent*100:.2f}%)")

        except Exception as e:
            log(f"❌ Erreur : {e}")

        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout bot for Backpack Exchange")
    parser.add_argument("symbol", type=str, help="Symbole (ex: BTC_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    args = parser.parse_args()

    main(args.symbol, real_run=args.real_run)
