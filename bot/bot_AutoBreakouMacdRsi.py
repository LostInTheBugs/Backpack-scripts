import time
import argparse
import os
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import numpy as np

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.public import Public, get_ohlcv

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20  # à adapter selon ta stratégie
PNL_THRESHOLD_CLOSE = 0.002  # 0.2%

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def prepare_ohlcv_df(ohlcv):
    df = pd.DataFrame(ohlcv)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def calculate_macd_rsi(df):
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['rsi'] = ta.rsi(df['close'], length=14)
    return df

def combined_signal(df):
    breakout = breakout_signal(df.to_dict('records'))
    macd_hist = df['MACDh_12_26_9'].iloc[-1]
    macd_signal = df['MACDs_12_26_9'].iloc[-1]
    macd_signal_bull = macd_hist > 0 and macd_hist > macd_signal
    macd_signal_bear = macd_hist < 0 and macd_hist < macd_signal
    rsi = df['rsi'].iloc[-1]

    if breakout == "BUY" and macd_signal_bull and rsi < 70:
        return "BUY"
    elif breakout == "SELL" and macd_signal_bear and rsi > 30:
        return "SELL"
    else:
        return None

def select_symbols_by_volatility(min_volume=1000, top_n=15, lookback=500):
    public = Public()
    markets = public.get_markets()
    perp_symbols = [m['symbol'] for m in markets if 'PERP' in m['symbol']]

    vol_list = []
    log(f"Calcul des volatilités pour {len(perp_symbols)} symbols PERP...")

    for symbol in perp_symbols:
        try:
            ohlcv = get_ohlcv(symbol, interval='1h', limit=lookback)
            if not ohlcv or len(ohlcv) < 30:
                continue
            df = prepare_ohlcv_df(ohlcv)
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            volatility = df['log_return'].std() * np.sqrt(24 * 365)  # annualisée pour hourly candles
            avg_volume = df['volume'].mean()
            if avg_volume < min_volume:
                continue
            vol_list.append((symbol, volatility, avg_volume))
        except Exception as e:
            log(f"Erreur sur {symbol}: {e}")

    vol_list.sort(key=lambda x: x[1], reverse=True)
    selected = vol_list[:top_n]

    log(f"Symbols sélectionnés (top {top_n} par volatilité et volume > {min_volume}):")
    for sym, vol, volm in selected:
        log(f"{sym} - Volatilité: {vol:.4f}, Volume moyen: {volm:.0f}")

    return [x[0] for x in selected]

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

def main(symbols: list, real_run: bool, auto_select=False):
    if auto_select:
        symbols = select_symbols_by_volatility()

    log(f"--- Breakout MACD RSI Bot started for symbols: {', '.join(symbols)} ---")
    log(f"Mode : {'real-run' if real_run else 'dry-run'}")

    while True:
        for symbol in symbols:
            handle_symbol(symbol, real_run)
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs='?', default="", help="Liste des symboles séparés par des virgules (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symbols par volatilité")
    args = parser.parse_args()

    if args.auto_select:
        symbols = []
    else:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    main(symbols, real_run=args.real_run, auto_select=args.auto_select)
