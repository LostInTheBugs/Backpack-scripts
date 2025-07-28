import pandas as pd

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

    trix_line, trix_signal = trix(df)

    if trix_line.iloc[-1] > trix_signal.iloc[-1]:
        return "BUY"
    elif trix_line.iloc[-1] < trix_signal.iloc[-1]:
        return "SELL"
    else:
        return "HOLD"
