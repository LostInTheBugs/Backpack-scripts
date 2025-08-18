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

    rsi_low_threshold = 35
    rsi_high_threshold = 65
    breakout_buffer = 0.01  # 1%

    if price < support * (1 + breakout_buffer) and rsi < rsi_low_threshold and trix > 0:
        log(f"🔄 BUY (Range, rebond support + TRIX) | Price={price:.4f} Support={support:.4f} RSI={rsi:.2f} TRIX={trix:.4f}", level="DEBUG")
        return "BUY"

    elif price > resistance * (1 - breakout_buffer) and rsi > rsi_high_threshold and trix < 0:
        log(f"🔄 SELL (Range, rejet resistance + TRIX) | Price={price:.4f} Resistance={resistance:.4f} RSI={rsi:.2f} TRIX={trix:.4f}", level="DEBUG")
        return "SELL"

    else:
        log(f"🔄 HOLD (Range) | Price={price:.4f} RSI={rsi:.2f} TRIX={trix:.4f}", level="DEBUG")
        return "HOLD"
