import pandas as pd
import ta

def prepare_indicators(df):
    """
    Prépare les indicateurs nécessaires au dataframe.
    """
    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    df['TRIX'] = ta.trend.trix(close=df['close'], window=15)
    df['High20'] = df['high'].rolling(window=20).max()
    df['Low20'] = df['low'].rolling(window=20).min()
    return df

def get_combined_signal(df):
    df = prepare_indicators(df)

    price = df['close'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    trix = df['TRIX'].iloc[-1]
    resistance = df['High20'].iloc[-1]
    support = df['Low20'].iloc[-1]

    # Seuils assouplis pour plus de signaux
    rsi_low_threshold = 42
    rsi_high_threshold = 58
    breakout_buffer = 0.03  # 3% autour des bornes
    trix_buy_threshold = -0.05
    trix_sell_threshold = 0.05

    # Signal d'achat souple
    if price < support * (1 + breakout_buffer) and rsi < rsi_low_threshold and trix > trix_buy_threshold:
        print(f"🟢 BUY (RangeSoft, rebond support souple) | Price={price:.4f} Support={support:.4f} RSI={rsi:.2f} TRIX={trix:.4f}")
        return "BUY"

    # Signal de vente souple
    elif price > resistance * (1 - breakout_buffer) and rsi > rsi_high_threshold and trix < trix_sell_threshold:
        print(f"🔴 SELL (RangeSoft, rejet resistance souple) | Price={price:.4f} Resistance={resistance:.4f} RSI={rsi:.2f} TRIX={trix:.4f}")
        return "SELL"

    else:
        print(f"⚪ HOLD (RangeSoft, conditions non réunies) | Price={price:.4f} RSI={rsi:.2f} TRIX={trix:.4f}")
        return "HOLD"
