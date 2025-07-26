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
PNL_THRESHOLD_CLOSE = 0.002  # 0.2%

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def prepare_ohlcv_df(ohlcv):
    df = pd.DataFrame(ohlcv)
    # Convertir les colonnes nécessaires en float (prévient les erreurs de type)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def calculate_macd_rsi(df):
    # MACD : fast=12, slow=26, signal=9 (valeurs par défaut)
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    # RSI période 14
    df['rsi'] = ta.rsi(df['close'], length=14)
    return df

def combined_signal(df):
    # Signal breakout simple basé sur close vs high/low précédent
    breakout = breakout_signal(df.to_dict('records'))

    # MACD crossover (macd > macd_signal = bullish)
    macd_hist = df['MACDh_12_26_9'].iloc[-1]
    macd_signal = df['MACDs_12_26_9'].iloc[-1]

    macd_signal_bull = macd_hist > 0 and macd_hist > macd_signal
    macd_signal_bear = macd_hist < 0 and macd_hist < macd_signal

    # RSI : Surachat < 70, Survente > 30 (classique)
    rsi = df['rsi'].iloc[-1]

    # Conditions combinées pour signal
    if breakout == "BUY" and macd_signal_bull and rsi < 70:
        return "BUY"
    elif breakout == "SELL" and macd_signal_bear and rsi > 30:
        return "SELL"
    else:
        return None

def handle_symbol(symbol: str, real_run: bool):
    try:
        ohlcv = get_ohlcv(symbol, interval="1m", limit=100)
        df = prepare_ohlcv_df(ohlcv)
        df = calculate_macd_rsi(df)

        signal = combined_signal(df)
        log(f"[{symbol}] Signal combiné retourné: {signal} ({type(signal)})")

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
            log(f"[{symbol}] 🕵️ Aucun signal breakout + MACD/RSI détecté.")

        if has_open_position(symbol):
            pnl = get_position_pnl(symbol)
            pnl_percent = pnl / POSITION_AMOUNT_USDC
            if pnl_percent >= PNL_THRESHOLD_CLOSE:
                log(f"[{symbol}] 🎯 PnL {pnl:.2f} USDC atteint ({pnl_percent*100:.2f}%). Fermeture de position.")
                if real_run:
                    close_position_percent(public_key, secret_key, symbol, 100)
                else:
                    log(f"[{symbol}] [Dry-run] Fermeture de position ignorée.")
            else:
                log(f"[{symbol}] 📊 PnL actuel : {pnl:.4f} USDC ({pnl_percent*100:.2f}%)")

    except Exception as e:
        log(f"[{symbol}] ❌ Erreur : {e}")

def main(symbols: list, real_run: bool):
    log(f"--- Breakout MACD RSI Bot started for symbols: {', '.join(symbols)} ---")
    log(f"Mode : {'real-run' if real_run else 'dry-run'}")

    while True:
        for symbol in symbols:
            handle_symbol(symbol, real_run)
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", type=str, help="Liste des symboles séparés par des virgules (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    main(symbols, real_run=args.real_run)
