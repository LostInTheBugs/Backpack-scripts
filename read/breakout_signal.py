def breakout_signal(ohlcv):
    if len(ohlcv) < 2:
        return None

    last = ohlcv[-1]
    prev = ohlcv[-2]

    # Convertir les valeurs en float si ce ne sont pas déjà des float
    last_close = float(last['close'])
    prev_high = float(prev['high'])
    prev_low = float(prev['low'])

    if last_close > prev_high:
        return "BUY"
    elif last_close < prev_low:
        return "SELL"
    return None
