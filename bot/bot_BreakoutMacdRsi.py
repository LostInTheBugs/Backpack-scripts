import time
import argparse
import os
from datetime import datetime

import pandas as pd
import pandas_ta as ta

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.public import get_ohlcv

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20  # à adapter selon ta stratégie
STOP_LOSS_PERCENT = 0.01  # stop loss suiveur à 1% par exemple

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def compute_indicators(ohlcv):
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"])
    df["macd_hist"] = macd["MACDh_12_26_9"]
    return df

def indicators_ok(df, signal):
    rsi = df["rsi"].iloc[-1]
    macd_hist = df["macd_hist"].iloc[-1]
    if signal == "BUY":
        return macd_hist > 0 and rsi < 70
    elif signal == "SELL":
        return macd_hist < 0 and rsi > 30
    return False

# Dictionnaire pour stocker le prix d'entrée et stop loss actuel par symbole
positions_info = {}

def handle_symbol(symbol: str, real_run: bool):
    global positions_info
    try:
        ohlcv = get_ohlcv(symbol, interval="1m", limit=100)
        signal = breakout_signal(ohlcv)
        log(f"[{symbol}] Signal brut retourné: {signal} ({type(signal)})")

        if signal in ["BUY", "SELL"]:
            df = compute_indicators(ohlcv)
            if not indicators_ok(df, signal):
                log(f"[{symbol}] Signal {signal} rejeté par MACD/RSI")
                return

            if has_open_position(symbol):
                log(f"[{symbol}] 🔄 Une position est déjà ouverte.")
            else:
                log(f"[{symbol}] 📈 Signal validé : {signal}. Ouverture d'une position.")
                if real_run:
                    direction = "long" if signal.lower() == "buy" else "short"
                    open_position(symbol, POSITION_AMOUNT_USDC, direction)
                    # Initialiser stop loss au prix d'entrée estimé (dernier close)
                    entry_price = ohlcv[-1][4]  # close price dernière bougie
                    positions_info[symbol] = {
                        "direction": direction,
                        "entry_price": entry_price,
                        "stop_loss": entry_price * (1 - STOP_LOSS_PERCENT) if direction == "long" else entry_price * (1 + STOP_LOSS_PERCENT)
                    }
                else:
                    log(f"[{symbol}] [Dry-run] Ouverture de position {signal.lower()} ignorée.")
        else:
            log(f"[{symbol}] 🕵️ Aucun signal breakout détecté.")

        # Gestion du stop loss suiveur
        if has_open_position(symbol):
            # Récupérer infos position
            info = positions_info.get(symbol)
            if not info:
                log(f"[{symbol}] ⚠️ Position ouverte mais infos stop loss manquantes, initialisation.")
                # On tente d'initialiser avec prix close actuel (risqué)
                entry_price = ohlcv[-1][4]
                direction = "long"  # hypothèse par défaut
                positions_info[symbol] = {
                    "direction": direction,
                    "entry_price": entry_price,
                    "stop_loss": entry_price * (1 - STOP_LOSS_PERCENT)
                }
                info = positions_info[symbol]

            direction = info["direction"]
            entry_price = info["entry_price"]
            stop_loss = info["stop_loss"]
            current_price = ohlcv[-1][4]

            if direction == "long":
                # Met à jour stop loss si le prix monte
                new_stop_loss = max(stop_loss, current_price * (1 - STOP_LOSS_PERCENT))
                if new_stop_loss != stop_loss:
                    log(f"[{symbol}] 📈 Stop loss mis à jour de {stop_loss:.6f} à {new_stop_loss:.6f}")
                    positions_info[symbol]["stop_loss"] = new_stop_loss
                # Si prix passe sous stop loss => fermeture position
                if current_price <= stop_loss:
                    log(f"[{symbol}] 🚨 Stop loss déclenché à {stop_loss:.6f} (prix actuel {current_price:.6f}), fermeture position.")
                    if real_run:
                        close_position_percent(public_key, secret_key, symbol, 100)
                        positions_info.pop(symbol, None)
                    else:
                        log(f"[{symbol}] [Dry-run] Fermeture position stop loss ignorée.")
            else:  # short
                # Met à jour stop loss si le prix descend
                new_stop_loss = min(stop_loss, current_price * (1 + STOP_LOSS_PERCENT))
                if new_stop_loss != stop_loss:
                    log(f"[{symbol}] 📉 Stop loss mis à jour de {stop_loss:.6f} à {new_stop_loss:.6f}")
                    positions_info[symbol]["stop_loss"] = new_stop_loss
                # Si prix passe au-dessus du stop loss => fermeture position
                if current_price >= stop_loss:
                    log(f"[{symbol}] 🚨 Stop loss déclenché à {stop_loss:.6f} (prix actuel {current_price:.6f}), fermeture position.")
                    if real_run:
                        close_position_percent(public_key, secret_key, symbol, 100)
                        positions_info.pop(symbol, None)
                    else:
                        log(f"[{symbol}] [Dry-run] Fermeture position stop loss ignorée.")

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
