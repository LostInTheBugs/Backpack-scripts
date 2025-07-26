import pandas as pd

def get_combined_signal(df):
    print("DEBUG get_combined_signal: Entrée dans la fonction")

    if df.empty or len(df) < 2:
        print("DEBUG DataFrame vide ou trop petit")
        return "HOLD"

    # Assure-toi que l'index est datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception as e:
            print(f"DEBUG Impossible de convertir l'index en datetime: {e}")
            return "HOLD"

    last_close = float(df['close'].iloc[-1])
    last_date = df.index[-1]

    min_close = float(df['close'].min())
    min_date = df['close'].idxmin()

    max_close = float(df['close'].max())
    max_date = df['close'].idxmax()

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