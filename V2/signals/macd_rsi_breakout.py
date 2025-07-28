def get_combined_signal(df):
    import pandas as pd
    import numpy as np

    # Assure DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    close = df['close']

    # --- Calcul MACD ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()

    # MACD crossover detection (sur les deux dernières valeurs)
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

    avg_gain = gain.rolling(window=window_length).mean()
    avg_loss = loss.rolling(window=window_length).mean()

    rs = avg_gain / (avg_loss + 1e-9)  # éviter division par zéro
    rsi = 100 - (100 / (1 + rs))

    rsi_curr = rsi.iloc[-1]

    # --- Logique de décision combinée ---
    # Conditions d'achat
    if macd_buy and rsi_curr < 40:
        return "BUY"

    # Conditions de vente
    if macd_sell and rsi_curr > 60:
        return "SELL"

    return "HOLD"