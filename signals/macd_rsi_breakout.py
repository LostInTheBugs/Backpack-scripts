def get_combined_signal(df):
    print("DEBUG get_combined_signal: Entrée dans la fonction")

    if df.empty or len(df) < 2:
        print("DEBUG DataFrame vide ou trop petit")
        return "HOLD"

    last_close = float(df['close'].iloc[-1])
    last_date = df.index[-1] if hasattr(df.index, 'strftime') else df.index[-1]
    
    min_close = float(df['close'].min())
    min_idx = df['close'].idxmin()
    min_date = min_idx if hasattr(min_idx, 'strftime') else min_idx

    max_close = float(df['close'].max())
    max_idx = df['close'].idxmax()
    max_date = max_idx if hasattr(max_idx, 'strftime') else max_idx

    print(f"DEBUG last_close={last_close} at {last_date}")
    print(f"DEBUG min_close={min_close} at {min_date}")
    print(f"DEBUG max_close={max_close} at {max_date}")

    if last_close >= max_close * 0.99:
        print("DEBUG Signal BUY détecté (last_close proche du max)")
        return "BUY"

    if last_close <= min_close * 1.01:
        print("DEBUG Signal SELL détecté (last_close proche du min)")
        return "SELL"

    print("DEBUG Pas de signal détecté, HOLD")
    return "HOLD"