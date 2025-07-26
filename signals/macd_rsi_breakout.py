def get_combined_signal(df):
    print("DEBUG get_combined_signal: Entrée dans la fonction")
    if df.empty or len(df) < 2:
        print("DEBUG DataFrame vide ou trop petit")
        return "HOLD"

    last_close = float(df['close'].iloc[-1])
    previous_close = float(df['close'].iloc[-2])

    print(f"DEBUG last_close={last_close}, previous_close={previous_close}")

    # Signal BUY si dernier close > précédent * 1.01 (hausse de 1%)
    if last_close > previous_close * 1.01:
        print("DEBUG Signal BUY détecté")
        return "BUY"

    # Signal SELL si dernier close < précédent * 0.99 (baisse de 1%)
    if last_close < previous_close * 0.99:
        print("DEBUG Signal SELL détecté")
        return "SELL"

    print("DEBUG Pas de signal détecté, HOLD")
    return "HOLD"
