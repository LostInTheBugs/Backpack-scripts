import pandas as pd

def calculate_trix(df, period=9):
    close = df['close']
    ema1 = close.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    trix = ema3.pct_change() * 100
    return trix

def get_combined_signal(df):
    df = df.copy()
    df['trix'] = calculate_trix(df)

    if len(df) < 2:
        return None

    last = df.iloc[-1]
    previous = df.iloc[-2]

    # Signal d'achat si TRIX croise à la hausse la ligne 0
    if previous['trix'] < 0 and last['trix'] > 0:
        return "BUY"
    elif previous['trix'] > 0 and last['trix'] < 0:
        return "SELL"
    else:
        return None
