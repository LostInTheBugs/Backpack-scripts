# signals/macd_rsi_breakout.py

def get_combined_signal(df):
    """
    Prend un DataFrame OHLCV, retourne l'un des signaux : 'BUY', 'SELL' ou 'HOLD'
    (logique simplifiée pour l'exemple)
    """
    # 🧠 TODO: implémentation réelle
    last_close = df['close'].iloc[-1]
    previous_close = df['close'].iloc[-2]

    if last_close > previous_close * 1.01:
        return "BUY"
    elif last_close < previous_close * 0.99:
        return "SELL"
    else:
        return "HOLD"
