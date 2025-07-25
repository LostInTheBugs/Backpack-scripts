import os
import sys
import time
import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backpack_public.public import get_ohlcv, get_position
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from list.orderbook_signal import breakout_signal

load_dotenv()
public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")
DEBUG_INDICATORS = True
TRAILING_STOP_PCT = 0.01
state = {}

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def calculate_macd_rsi(df):
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['ma20'] = ta.sma(df['close'], length=20)
    df['ma200'] = ta.sma(df['close'], length=200)
    return df

def is_trending(df, signal):
    ma_short = df['ma20'].iloc[-1]
    ma_long = df['ma200'].iloc[-1]
    if signal == "BUY" and ma_short > ma_long:
        return True
    elif signal == "SELL" and ma_short < ma_long:
        return True
    return False

def combined_signal(df):
    breakout = breakout_signal(df.to_dict('records'))
    macd_hist = df['MACDh_12_26_9'].iloc[-1]
    rsi = df['rsi'].iloc[-1]

    last_candle = df.iloc[-1]
    body_size = abs(last_candle['close'] - last_candle['open'])
    total_range = last_candle['high'] - last_candle['low']
    body_ratio = body_size / total_range if total_range > 0 else 0

    if DEBUG_INDICATORS:
        print(f"📉 Indicateurs: RSI={rsi:.2f}, MACDh={macd_hist:.5f}, Breakout={breakout}, Body ratio={body_ratio:.2f}")

    if body_ratio < 0.5:
        return None

    macd_bull = macd_hist > 0
    macd_bear = macd_hist < 0

    if breakout == "BUY" and macd_bull and rsi < 60 and is_trending(df, "BUY"):
        return "BUY"
    elif breakout == "SELL" and macd_bear and rsi > 40 and is_trending(df, "SELL"):
        return "SELL"
    else:
        return None

def handle_symbol(symbol, real_run):
    df = get_ohlcv(symbol, interval="1m", limit=300)
    if df is None or len(df) < 100:
        return

    df = calculate_macd_rsi(df)
    signal = combined_signal(df)

    log(f"[{symbol}] Signal combiné: {signal}")

    if symbol not in state:
        state[symbol] = {}

    symbol_state = state[symbol]
    position = get_position(public_key, secret_key, symbol)

    if position:
        entry_price = float(position['entryPrice'])
        current_price = float(df['close'].iloc[-1])
        unrealized_pnl = (current_price - entry_price) / entry_price if position['side'] == 'long' else (entry_price - current_price) / entry_price

        if 'entry_price' not in symbol_state:
            symbol_state['entry_price'] = entry_price
            symbol_state['max_price'] = entry_price
            symbol_state['tp_hit'] = []

        if position['side'] == 'long':
            symbol_state['max_price'] = max(symbol_state['max_price'], current_price)

            TP_LEVELS = [0.01, 0.02, 0.03]
            for level in TP_LEVELS:
                if level not in symbol_state['tp_hit'] and current_price >= symbol_state['entry_price'] * (1 + level):
                    symbol_state['tp_hit'].append(level)
                    log(f"[{symbol}] 🎯 Take profit atteint à +{level*100:.1f}%")
                    if real_run:
                        close_position_percent(public_key, secret_key, symbol, 33)
                    else:
                        log(f"[{symbol}] [Dry-run] Clôture partielle à +{level*100:.1f}% ignorée.")

            if current_price < symbol_state['max_price'] * (1 - TRAILING_STOP_PCT):
                log(f"[{symbol}] 🔻 Stop suiveur déclenché. Clôture de la position.")
                if real_run:
                    close_position_percent(public_key, secret_key, symbol, 100)
                else:
                    log(f"[{symbol}] [Dry-run] Clôture simulée.")
                symbol_state.clear()

    elif signal in ("BUY", "SELL"):
        log(f"[{symbol}] 🟢 Ouverture d'une position {signal}.")
        if real_run:
            open_position(public_key, secret_key, symbol, direction=signal.lower(), usdc_amount=10)
        else:
            log(f"[{symbol}] [Dry-run] Ouverture simulée.")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('symbols', type=str, help="Liste de symboles séparés par des virgules")
    parser.add_argument('--real-run', action='store_true', help="Mode réel")
    args = parser.parse_args()

    symbols = args.symbols.split(",")
    real_run = args.real_run

    while True:
        for symbol in symbols:
            try:
                handle_symbol(symbol, real_run)
            except Exception as e:
                log(f"[{symbol}] ❌ Erreur : {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
