import time 
import argparse
import os
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import numpy as np
import math
import requests

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
        df[col] = df[col].astype(float)
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

def get_perp_symbols():
    url = "https://api.backpack.exchange/api/v1/markets"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        return [m['symbol'] for m in markets if 'PERP' in m['symbol']]
    except Exception as e:
        log(f"Erreur récupération symbols PERP: {e}")
        return []

def select_symbols_by_volatility(min_volume=1000, top_n=15, lookback=500):
    perp_symbols = get_perp_symbols()
    vol_list = []
    log(f"🔎 Calcul des volatilités pour {len(perp_symbols)} symbols PERP...")

    for symbol in perp_symbols:
        try:
            ohlcv = get_ohlcv(symbol, interval='1h', limit=lookback)
            if not ohlcv or len(ohlcv) < 30:
                continue
            df = prepare_ohlcv_df(ohlcv)
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            volatility = df['log_return'].std() * np.sqrt(24 * 365)
            avg_volume = df['volume'].mean()
            if avg_volume < min_volume:
                continue
            vol_list.append((symbol, volatility, avg_volume))
        except Exception as e:
            log(f"⚠️ Erreur sur {symbol}: {e}")

    vol_list.sort(key=lambda x: x[1], reverse=True)
    selected = vol_list[:top_n]

    log(f"✅ Symbols sélectionnés (top {top_n} par volatilité et volume > {min_volume}):")
    for sym, vol, volm in selected:
        log(f"• {sym} - Volatilité: {vol:.4f}, Volume moyen: {volm:.0f}")

    return [x[0] for x in selected]

def handle_symbol(symbol: str, real_run: bool):
    try:
        ohlcv = get_ohlcv(symbol, interval="1m", limit=100)
        df = prepare_ohlcv_df(ohlcv)
        df = calculate_macd_rsi(df)

        signal = combined_signal(df)
        log(f"[{symbol}] Signal combiné: {signal}")

        if not hasattr(handle_symbol, "trailing_stop_state"):
            handle_symbol.trailing_stop_state = {}
        state = handle_symbol.trailing_stop_state.setdefault(symbol, {
            "position": None,
            "entry_price": 0.0,
            "max_price": 0.0,
            "min_price": float('inf')
        })

        if signal in ["BUY", "SELL"]:
            if state["position"] is None:
                state["position"] = "long" if signal == "BUY" else "short"
                state["entry_price"] = df['close'].iloc[-1]
                state["max_price"] = state["entry_price"]
                state["min_price"] = state["entry_price"]
                log(f"[{symbol}] 📈 Ouverture position {state['position']} à {state['entry_price']:.4f}")
                if real_run:
                    direction = "long" if state["position"] == "long" else "short"
                    open_position(symbol, POSITION_AMOUNT_USDC, direction)
            else:
                log(f"[{symbol}] ⚠️ Déjà en position {state['position']}")
        else:
            log(f"[{symbol}] 🕵️ Aucun signal d'ouverture.")

        if state["position"] is not None:
            current_price = df['close'].iloc[-1]
            if state["position"] == "long":
                if current_price > state["max_price"]:
                    state["max_price"] = current_price
                    log(f"[{symbol}] 🔝 Nouveau max prix {state['max_price']:.4f}")
                if current_price < state["max_price"] * (1 - TRAILING_STOP_PCT):
                    pnl = (current_price - state["entry_price"]) / state["entry_price"]
                    log(f"[{symbol}] 🚪 Stop suiveur déclenché LONG à {current_price:.4f}, PnL: {pnl:.4%}")
                    if real_run:
                        close_position_percent(public_key, secret_key, symbol, 100)
                    else:
                        log(f"[{symbol}] [Dry-run] Fermeture LONG ignorée.")
                    state["position"] = None
                    state["entry_price"] = 0.0
                    state["max_price"] = 0.0
                    state["min_price"] = float('inf')
            elif state["position"] == "short":
                if current_price < state["min_price"]:
                    state["min_price"] = current_price
                    log(f"[{symbol}] 🔝 Nouveau min prix {state['min_price']:.4f}")
                if current_price > state["min_price"] * (1 + TRAILING_STOP_PCT):
                    pnl = (state["entry_price"] - current_price) / state["entry_price"]
                    log(f"[{symbol}] 🚪 Stop suiveur déclenché SHORT à {current_price:.4f}, PnL: {pnl:.4%}")
                    if real_run:
                        close_position_percent(public_key, secret_key, symbol, 100)
                    else:
                        log(f"[{symbol}] [Dry-run] Fermeture SHORT ignorée.")
                    state["position"] = None
                    state["entry_price"] = 0.0
                    state["max_price"] = 0.0
                    state["min_price"] = float('inf')

    except Exception as e:
        log(f"[{symbol}] ❌ Erreur : {e}")

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
            df_slice = df.iloc[:i+1].copy()
            # Calculer l'EMA50 sur la tranche
            df_slice['ema50'] = ta.ema(df_slice['close'], length=50)
            macd_df = ta.macd(df_slice['close'])
            df_slice['macd'] = macd_df.iloc[:, 0]
            df_slice['macd_signal'] = macd_df.iloc[:, 1]
            df_slice['rsi'] = ta.rsi(df_slice['close'], length=14)

            last_row = df_slice.iloc[-1]
            # Vérification de NaN ou None dans les valeurs importantes
            if any(pd.isna(last_row[col]) for col in ['ema50', 'macd', 'macd_signal', 'rsi', 'close']):
                continue

            signal = combined_signal(df_slice)
            close_price = last_row['close']

            if close_price is None or pd.isna(close_price):
                continue

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
                    if max_price is None:
                        max_price = close_price
                    if close_price > max_price:
                        max_price = close_price
                    if max_price is not None and close_price < max_price * (1 - TRAILING_STOP_PCT):
                        if (
                            entry_price is not None and not pd.isna(entry_price)
                            and close_price is not None and not pd.isna(close_price)
                        ):
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
                    if signal == "SELL":
                        if entry_price is not None and close_price is not None and not pd.isna(entry_price) and not pd.isna(close_price):
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
                elif position == "short":
                    if min_price is None:
                        min_price = close_price
                    if close_price < min_price:
                        min_price = close_price
                    if min_price is not None and close_price > min_price * (1 + TRAILING_STOP_PCT):
                        if entry_price is not None and close_price is not None and not pd.isna(entry_price) and not pd.isna(close_price):
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
                    if signal == "BUY":
                        if entry_price is not None and close_price is not None and not pd.isna(entry_price) and not pd.isna(close_price):
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

        # Clôturer position ouverte à la fin du backtest
        if position is not None:
            exit_price = df['close'].iloc[-1]
            # FIX: check exit_price and entry_price are not None or NaN
            if (
                exit_price is not None and not pd.isna(exit_price)
                and entry_price is not None and not pd.isna(entry_price)
            ):
                if position == "long":
                    pnl = (exit_price - entry_price) / entry_price
                else:
                    pnl = (entry_price - exit_price) / entry_price
                trades.append({
                    "type": position,
                    "entry": entry_price,
                    "exit": exit_price,
                    "pnl": pnl
                })

        # Remove trades with None or NaN values
        trades = [
            t for t in trades
            if t["entry"] is not None and not pd.isna(t["entry"])
            and t["exit"] is not None and not pd.isna(t["exit"])
            and t["pnl"] is not None and not pd.isna(t["pnl"])
        ]

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





def main(symbols: list, real_run: bool, auto_select=False):
    last_selection_time = 0

    while True:
        if auto_select and (time.time() - last_selection_time > RESELECT_INTERVAL_SEC):
            symbols = select_symbols_by_volatility()
            last_selection_time = time.time()
            log(f"🔄 Nouvelle sélection automatique de symbols : {', '.join(symbols)}")

        for symbol in symbols:
            handle_symbol(symbol, real_run)

        time.sleep(1)

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
            symbols = select_symbols_by_volatility()  # FIX: initialize symbols for auto-select
        else:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        main(symbols, real_run=args.real_run, auto_select=args.auto_select)
