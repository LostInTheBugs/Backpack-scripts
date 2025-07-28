import pandas as pd
import numpy as np

def get_combined_signal(df: pd.DataFrame) -> str:
    """
    Calcule MACD, RSI et Breakout sur données 1 seconde (sans resample),
    puis retourne un signal simple: "BUY", "SELL" ou "HOLD".
    """
    if df.empty or len(df) < 50:
        return "HOLD"  # Pas assez de données pour calculs

    close = df['close']

    # --- MACD ---
    exp1 = close.ewm(span=12*60, adjust=False).mean()  # MACD fast EMA sur 12 minutes (720s)
    exp2 = close.ewm(span=26*60, adjust=False).mean()  # MACD slow EMA sur 26 minutes (1560s)
    macd = exp1 - exp2
    signal_line = macd.ewm(span=9*60, adjust=False).mean()  # Signal line sur 9 minutes (540s)

    macd_hist = macd - signal_line

    # --- RSI ---
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    window_length = 14 * 60  # RSI sur 14 minutes = 840 secondes
    avg_gain = gain.rolling(window=window_length, min_periods=1).mean()
    avg_loss = loss.rolling(window=window_length, min_periods=1).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))

    # --- Breakout simple ---
    # Prix max des dernières 60 minutes (3600s)
    breakout_window = 60 * 60
    highest_high = df['high'].rolling(window=breakout_window, min_periods=1).max()
    lowest_low = df['low'].rolling(window=breakout_window, min_periods=1).min()

    # Dernier prix close
    last_close = close.iloc[-1]

    # Critères pour signal
    # MACD bullish si macd_hist > 0, bearish si < 0
    macd_bull = macd_hist.iloc[-1] > 0
    macd_bear = macd_hist.iloc[-1] < 0

    # RSI overbought/sold zones
    rsi_val = rsi.iloc[-1]
    rsi_oversold = rsi_val < 30
    rsi_overbought = rsi_val > 70

    # Breakout : breakout haussier si last_close dépasse highest_high précédent
    breakout_up = last_close > highest_high.iloc[-2] if len(highest_high) > 1 else False
    breakout_down = last_close < lowest_low.iloc[-2] if len(lowest_low) > 1 else False

    # Synthèse simple :
    if macd_bull and rsi_oversold and breakout_up:
        return "BUY"
    elif macd_bear and rsi_overbought and breakout_down:
        return "SELL"
    else:
        return "HOLD"
