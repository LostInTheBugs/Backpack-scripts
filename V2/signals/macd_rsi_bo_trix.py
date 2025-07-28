import pandas as pd

def calculate_macd(df, fast=12, slow=26, signal=9):
    df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    return df

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def calculate_trix(df, period=9):
    ema1 = df['close'].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    df['trix'] = ema3.pct_change() * 100
    return df

def get_combined_signal(df):
    df = df.copy()
    df = calculate_macd(df)
    df = calculate_rsi(df)
    df = calculate_trix(df)

    if len(df) < 2:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    macd_buy = prev['macd'] < prev['signal'] and last['macd'] > last['signal']
    macd_sell = prev['macd'] > prev['signal'] and last['macd'] < last['signal']

    rsi_buy = last['rsi'] < 30
    rsi_sell = last['rsi'] > 70

    breakout_buy = last['close'] > df['high'][-20:-1].max()
    breakout_sell = last['close'] < df['low'][-20:-1].min()

    trix_buy = prev['trix'] < 0 and last['trix'] > 0
    trix_sell = prev['trix'] > 0 and last['trix'] < 0

    if macd_buy and rsi_buy and breakout_buy and trix_buy:
        return "BUY"
    elif macd_sell and rsi_sell and breakout_sell and trix_sell:
        return "SELL"
    else:
        return None
