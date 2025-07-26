def get_combined_signal(df):
    print("DEBUG get_combined_signal: Entrée dans la fonction")

    if df.empty or len(df) < 2:
        print("DEBUG DataFrame vide ou trop petit")
        return "HOLD"

    last_close = float(df['close'].iloc[-1])
    min_close = float(df['close'].min())
    max_close = float(df['close'].max())

    print(f"DEBUG last_close={last_close}, min_close={min_close}, max_close={max_close}")

    # Signal BUY si dernière clôture est proche du max (breakout haussier)
    if last_close >= max_close * 0.99:
        print("DEBUG Signal BUY détecté (last_close proche du max)")
        return "BUY"

    # Signal SELL si dernière clôture est proche du min (breakout baissier)
    if last_close <= min_close * 1.01:
        print("DEBUG Signal SELL détecté (last_close proche du min)")
        return "SELL"

    print("DEBUG Pas de signal détecté, HOLD")
    return "HOLD"
