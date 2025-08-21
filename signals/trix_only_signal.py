# signals/trix_only_signal.py
from indicators.combined_indicators import calculate_trix

def get_combined_signal(df, symbol):
    df = df.copy()
    df = calculate_trix(df)

    if len(df) < 2:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if prev['trix'] < 0 and last['trix'] > 0:
        return "BUY"
    elif prev['trix'] > 0 and last['trix'] < 0:
        return "SELL"
    else:
        return None
