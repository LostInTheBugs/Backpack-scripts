import pandas as pd
from indicators.range_indicators import compute_range_indicators
from utils.logger import log

def get_combined_signal(df, symbol):
    df = compute_range_indicators(df)

    price = df['close'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    trix = df['TRIX'].iloc[-1]
    resistance = df['High20'].iloc[-1]
    support = df['Low20'].iloc[-1]

    rsi_low_threshold = 42
    rsi_high_threshold = 58
    breakout_buffer = 0.03  # 3%
    trix_buy_threshold = -0.05
    trix_sell_threshold = 0.05

    if price < support * (1 + breakout_buffer) and rsi < rsi_low_threshold and trix > trix_buy_threshold:
        log(f"[INFO] 🟢 BUY (RangeSoft, rebond support souple) | Price={price:.4f} Support={support:.4f} RSI={rsi:.2f} TRIX={trix:.4f}", level="INFO")
        return "BUY"

    elif price > resistance * (1 - breakout_buffer) and rsi > rsi_high_threshold and trix < trix_sell_threshold:
        log(f"[INFO] 🔴 SELL (RangeSoft, rejet resistance souple) | Price={price:.4f} Resistance={resistance:.4f} RSI={rsi:.2f} TRIX={trix:.4f}", level="INFO")
        return "SELL"

    else:
        log(f"[INFO] ⚪ HOLD (RangeSoft) | Price={price:.4f} RSI={rsi:.2f} TRIX={trix:.4f}", level="INFO")
        return "HOLD"
