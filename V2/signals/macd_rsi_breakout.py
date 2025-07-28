def get_combined_signal(df):
    import pandas as pd
    import numpy as np

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    close = df['close']

    # Minimum 26 valeurs pour EMA26 (la plus longue EMA)
    if len(close) < 26:
        return "HOLD"  # Pas assez de données pour calcul MACD

    # --- Calcul MACD ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()

    # Vérifie qu'on a au moins 2 valeurs pour détecter croisement
    if len(macd) < 2 or len(signal_line) < 2:
        return "HOLD"

    macd_prev = macd.iloc[-2]
    signal_prev = signal_line.iloc[-2]
    macd_curr = macd.iloc[-1]
    signal_curr = signal_line.iloc[-1]

    macd_buy = (macd_prev < signal_prev) and (macd_curr > signal_curr)
    macd_sell = (macd_prev > signal_prev) and (macd_curr < signal_curr)

    # --- Calcul RSI ---
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    window_length = 14

    if len(close) < window_length:
        return "HOLD"  # Pas assez de données pour RSI

    avg_gain = gain.rolling(window=window_length).mean()
    avg_loss = loss.rolling(window=window_length).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    rsi_curr = rsi.iloc[-1]

    # --- Logique de décision combinée ---
    if macd_buy and rsi_curr < 40:
        return "BUY"

    if macd_sell and rsi_curr > 60:
        return "SELL"

    return "HOLD"
