from indicators.combined_indicators import compute_all

def get_combined_signal(df):
    df = df.copy()
    df = compute_all(df)

    if len(df) < 2:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    macd_buy = prev['macd'] < prev['signal'] and last['macd'] > last['signal']
    macd_sell = prev['macd'] > prev['signal'] and last['macd'] < last['signal']

    rsi_buy = last['rsi'] < 30
    rsi_sell = last['rsi'] > 70

    breakout_buy = last['close'] > df['high_breakout'][-20:-1].max()
    breakout_sell = last['close'] < df['low_breakout'][-20:-1].min()

    trix_buy = prev['trix'] < 0 and last['trix'] > 0
    trix_sell = prev['trix'] > 0 and last['trix'] < 0

    if macd_buy and rsi_buy and breakout_buy and trix_buy:
        return "BUY"
    elif macd_sell and rsi_sell and breakout_sell and trix_sell:
        return "SELL"
    else:
        return None
