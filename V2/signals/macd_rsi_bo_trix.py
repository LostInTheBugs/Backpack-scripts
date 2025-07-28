import pandas as pd

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def breakout(df):
    last_close = df['close'].iloc[-1]
    if last_close > df['close'].max() * 0.99:
        return "BUY"
    elif last_close < df['close'].min() * 1.01:
        return "SELL"
    return "HOLD"

def trix(df, length=15, signal=9):
    close = df['close']
    ema1 = close.ewm(span=length, adjust=False).mean()
    ema2 = ema1.ewm(span=length, adjust=False).mean()
    ema3 = ema2.ewm(span=length, adjust=False).mean()
    trix_line = 100 * (ema3 - ema3.shift(1)) / ema3.shift(1)
    trix_signal = trix_line.ewm(span=signal, adjust=False).mean()
    return trix_line, trix_signal

def get_combined_signal(df):
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    macd_line, macd_signal = calculate_macd(df)
    rsi = calculate_rsi(df)
    trix_line, trix_signal = trix(df)
    bo_signal = breakout(df)

    latest_macd = macd_line.iloc[-1] > macd_signal.iloc[-1]
    latest_rsi = rsi.iloc[-1] < 30 or rsi.iloc[-1] > 70
    latest_trix = trix_line.iloc[-1] > trix_signal.iloc[-1]
    latest_bo = bo_signal

    if latest_macd and latest_trix and latest_rsi and latest_bo == "BUY":
        return "BUY"
    elif not latest_macd and not latest_trix and latest_rsi and latest_bo == "SELL":
        return "SELL"
    else:
        return "HOLD"
