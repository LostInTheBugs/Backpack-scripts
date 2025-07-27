def get_combined_signal(df):
    import pandas as pd
#    print("DEBUG get_combined_signal: Entrée dans la fonction")
#    print("DEBUG index type:", type(df.index))
#    print("DEBUG index head:", df.index[:5])

    # Assure-toi que l'index est DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    last_close = df['close'].iloc[-1]
    last_close_date = df.index[-1]

    min_close = df['close'].min()
    min_close_date = df['close'].idxmin()

    max_close = df['close'].max()
    max_close_date = df['close'].idxmax()

#    print(f"DEBUG last_close={last_close} at {last_close_date}")
#    print(f"DEBUG min_close={min_close} at {min_close_date}")
#    print(f"DEBUG max_close={max_close} at {max_close_date}")

    # Exemple de condition simple
    if last_close > max_close * 0.99:
        print("DEBUG Signal BUY détecté (last_close proche du max)")
        return "BUY"
    elif last_close < min_close * 1.01:
        print("DEBUG Signal SELL détecté (last_close proche du min)")
        return "SELL"
    else:
        print("DEBUG Pas de signal détecté, HOLD")
        return "HOLD"
