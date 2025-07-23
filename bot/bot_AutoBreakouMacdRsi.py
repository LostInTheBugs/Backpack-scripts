import time
import argparse
import os
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import numpy as np
import requests

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.public import get_ohlcv

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20
PNL_THRESHOLD_CLOSE = 0.002
RESELECT_INTERVAL_SEC = 300  # 5 minutes

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

        if signal in ["BUY", "SELL"]:
            if has_open_position(symbol):
                log(f"[{symbol}] ⚠️ Déjà en position.")
            else:
                log(f"[{symbol}] 📈 Signal {signal}. Ouverture.")
                if real_run:
                    direction = "long" if signal.lower() == "buy" else "short"
                    open_position(symbol, POSITION_AMOUNT_USDC, direction)
                else:
                    log(f"[{symbol}] [Dry-run] Ouverture ignorée.")
        else:
            log(f"[{symbol}] 🕵️ Aucun signal exploitable.")

        if has_open_position(symbol):
            pnl = get_position_pnl(symbol)
            pnl_percent = pnl / POSITION_AMOUNT_USDC
            if pnl_percent >= PNL_THRESHOLD_CLOSE:
                log(f"[{symbol}] 🎯 PnL {pnl:.2f} USDC atteint ({pnl_percent*100:.2f}%). Fermeture.")
                if real_run:
                    close_position_percent(public_key, secret_key, symbol, 100)
                else:
                    log(f"[{symbol}] [Dry-run] Fermeture ignorée.")
            else:
                log(f"[{symbol}] 🔍 PnL : {pnl:.4f} USDC ({pnl_percent*100:.2f}%)")

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

        trades = []  # liste des trades simulés: dict avec type, entry_price, exit_price
        position = None  # None, "long" ou "short"
        entry_price = 0.0

        for i in range(30, len(df)):
            df_slice = df.iloc[:i+1]
            signal = combined_signal(df_slice)
            close_price = df_slice['close'].iloc[-1]

            if position is None:
                # On ouvre une position si signal BUY ou SELL
                if signal == "BUY":
                    position = "long"
                    entry_price = close_price
                elif signal == "SELL":
                    position = "short"
                    entry_price = close_price
            else:
                # Si position ouverte, on ferme si signal inverse ou pas de signal
                if (position == "long" and signal == "SELL") or (position == "short" and signal == "BUY") or signal is None:
                    exit_price = close_price
                    trades.append({
                        "type": position,
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl": (exit_price - entry_price) / entry_price if position == "long" else (entry_price - exit_price) / entry_price
                    })
                    position = None
                    entry_price = 0.0

        # Si position ouverte en fin de données, on la ferme à la dernière clôture
        if position is not None:
            exit_price = df['close'].iloc[-1]
            trades.append({
                "type": position,
                "entry": entry_price,
                "exit": exit_price,
                "pnl": (exit_price - entry_price) / entry_price if position == "long" else (entry_price - exit_price) / entry_price
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
            symbols = []
        else:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        main(symbols, real_run=args.real_run, auto_select=args.auto_select)
