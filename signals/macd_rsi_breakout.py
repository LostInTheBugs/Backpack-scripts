from indicators.combined_indicators import compute_all

def get_combined_signal(df, symbol):
    if df.empty or len(df) < 50:
        return "HOLD"

    # Passe le symbole pour un logging plus précis
    df = compute_all(df, symbol=symbol)

    close = df['close']

    macd_hist = df['macd'] - df['signal']

    rsi_val = df['rsi'].iloc[-1]

    highest_high = df['high_breakout']
    lowest_low = df['low_breakout']

    last_close = close.iloc[-1]

    macd_bull = macd_hist.iloc[-1] > 0
    macd_bear = macd_hist.iloc[-1] < 0

    rsi_oversold = rsi_val < 30
    rsi_overbought = rsi_val > 70

    breakout_up = last_close > highest_high.iloc[-2] if len(highest_high) > 1 else False
    breakout_down = last_close < lowest_low.iloc[-2] if len(lowest_low) > 1 else False

    if macd_bull and rsi_oversold and breakout_up:
        return "BUY"
    elif macd_bear and rsi_overbought and breakout_down:
        return "SELL"
    else:
        return "HOLD"

