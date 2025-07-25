import time
import argparse
import os
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import numpy as np
import requests
import math  # IMPORTANT pour isnan

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.public import get_ohlcv

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20
RESELECT_INTERVAL_SEC = 300  # 5 minutes
TRAILING_STOP_PCT = 0.005  # 0.5% stop suiveur

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def prepare_ohlcv_df(ohlcv):
    df = pd.DataFrame(ohlcv)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def calculate_macd_rsi(df):
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['rsi'] = ta.rsi(df['close'], length=14)
    return df

def combined_signal(df):
    df = df.copy()
    df['ema50'] = ta.ema(df['close'], length=50)
    macd_df = ta.macd(df['close'])
    df['macd'] = macd_df.iloc[:, 0]
    df['macd_signal'] = macd_df.iloc[:, 1]
    df['rsi'] = ta.rsi(df['close'], length=14)

    if df[['ema50', 'macd', 'macd_signal', 'rsi']].iloc[-1].isnull().any():
        return None

    signal = None

    if df['high'].iloc[-1] > df['high'].iloc[-2] and df['close'].iloc[-1] > df['high'].iloc[-2]:
        if df['close'].iloc[-1] < df['ema50'].iloc[-1]:
            print(f"❌ Signal BUY rejeté : close ({df['close'].iloc[-1]:.4f}) < ema50 ({df['ema50'].iloc[-1]:.4f})")
        elif df['macd'].iloc[-1] <= df['macd_signal'].iloc[-1]:
            print("❌ Signal BUY rejeté : MACD haussier absent")
        elif df['rsi'].iloc[-1] > 70:
            print("❌ Signal BUY rejeté : RSI trop élevé")
        else:
            signal = 'BUY'

    elif df['low'].iloc[-1] < df['low'].iloc[-2] and df['close'].iloc[-1] < df['low'].iloc[-2]:
        if df['close'].iloc[-1] >= df['ema50'].iloc[-1]:
            print(f"❌ Signal SELL rejeté : close ({df['close'].iloc[-1]:.4f}) >= ema50 ({df['ema50'].iloc[-1]:.4f})")
        elif df['macd'].iloc[-1] >= df['macd_signal'].iloc[-1]:
            print("❌ Signal SELL rejeté : MACD baissier absent")
        elif df['rsi'].iloc[-1] < 30:
            print("❌ Signal SELL rejeté : RSI trop bas")
        else:
            signal = 'SELL'

    return signal

def duration_to_minutes(duration: str) -> int:
    if duration.endswith("m"):
        return int(duration[:-1])
    elif duration.endswith("h"):
        return int(duration[:-1]) * 60
    elif duration.endswith("d"):
        return int(duration[:-1]) * 60 * 24
    elif duration.endswith("w"):
        return int(duration[:-1]) * 60 * 24 * 7
    else:
        raise ValueError("Durée non reconnue. Utilise 1h, 1d, 1w ou 1m.")

def backtest_symbol(symbol: str, duration: str):
    try:
        minutes = duration_to_minutes(duration)
        limit = min(minutes, 1000)
        ohlcv = get_ohlcv(symbol, interval="1m", limit=limit)
        df = prepare_ohlcv_df(ohlcv)
        df = calculate_macd_rsi(df)

        trades = []
        position = None
        entry_price = None
        max_price = None
        min_price = None

        for i in range(30, len(df)):
            df_slice = df.iloc[:i+1]
            signal = combined_signal(df_slice)
            close_price = df_slice['close'].iloc[-1]

            # Debug log
            # print(f"[DEBUG {symbol}] i={i}, pos={position}, close={close_price}, entry={entry_price}, max={max_price}, min={min_price}, signal={signal}")

            if position is None:
                if signal == "BUY":
                    position = "long"
                    entry_price = close_price
                    max_price = entry_price
                    min_price = entry_price
                elif signal == "SELL":
                    position = "short"
                    entry_price = close_price
                    max_price = entry_price
                    min_price = entry_price
            else:
                if position == "long":
                    if close_price > max_price:
                        max_price = close_price
                    if entry_price is None or close_price is None:
                        continue
                    if math.isnan(entry_price) or math.isnan(close_price):
                        continue
                    if close_price < max_price * (1 - TRAILING_STOP_PCT):
                        pnl = (close_price - entry_price) / entry_price
                        trades.append({
                            "type": position,
                            "entry": entry_price,
                            "exit": close_price,
                            "pnl": pnl
                        })
                        position = None
                        entry_price = None
                        max_price = None
                        min_price = None
                        continue
                    if signal is not None and signal == "SELL":
                        pnl = (close_price - entry_price) / entry_price
                        trades.append({
                            "type": position,
                            "entry": entry_price,
                            "exit": close_price,
                            "pnl": pnl
                        })
                        position = None
                        entry_price = None
                        max_price = None
                        min_price = None
                elif position == "short":
                    if close_price < min_price:
                        min_price = close_price
                    if entry_price is None or close_price is None:
                        continue
                    if math.isnan(entry_price) or math.isnan(close_price):
                        continue
                    if close_price > min_price * (1 + TRAILING_STOP_PCT):
                        pnl = (entry_price - close_price) / entry_price
                        trades.append({
                            "type": position,
                            "entry": entry_price,
                            "exit": close_price,
                            "pnl": pnl
                        })
                        position = None
                        entry_price = None
                        max_price = None
                        min_price = None
                        continue
                    if signal is not None and signal == "BUY":
                        pnl = (entry_price - close_price) / entry_price
                        trades.append({
                            "type": position,
                            "entry": entry_price,
                            "exit": close_price,
                            "pnl": pnl
                        })
                        position = None
                        entry_price = None
                        max_price = None
                        min_price = None

        if position is not None and entry_price is not None:
            exit_price = df['close'].iloc[-1]
            if exit_price is not None and not math.isnan(exit_price):
                pnl = (exit_price - entry_price) / entry_price if position == "long" else (entry_price - exit_price) / entry_price
                trades.append({
                    "type": position,
                    "entry": entry_price,
                    "exit": exit_price,
                    "pnl": pnl
                })

        total_trades = len(trades)
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
        total_pnl = sum([t['pnl'] for t in trades])

        log(f"[{symbol}] 📊 Backtest {duration} : {total_trades} trades, {len(wins)} gagnants, {len(losses)} perdants, "
            f"Win rate: {win_rate:.2f}%, Gain moyen: {avg_win:.4f}, Perte moyenne: {avg_loss:.4f}, PnL total: {total_pnl:.4f}")

    except Exception as e:
        log(f"[{symbol}] ❌ Erreur backtest : {e}")

# --- Le reste de ton script (handle_symbol, main, etc.) reste inchangé ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs='?', default="", help="Liste des symboles séparés par des virgules (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symbols par volatilité")
    parser.add_argument("--backtest", type=str, help="Backtest sur une période: 1h, 1d, 1w, 1m")
    args = parser.parse_args()

    if args.backtest:
        duration = args.backtest
        if args.auto_select:
            symbols = select_symbols_by_volatility()
        else:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        for symbol in symbols:
            backtest_symbol(symbol, duration)
    else:
        if args.auto_select:
            symbols = []
        else:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        main(symbols, real_run=args.real_run, auto_select=args.auto_select)
