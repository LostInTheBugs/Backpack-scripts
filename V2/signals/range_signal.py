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

    # Seuils ajustables
    rsi_low_threshold = 35
    rsi_high_threshold = 65
    breakout_buffer = 0.01  # 1%

    # Achat si proche du support, RSI bas, et TRIX positif (rebond)
    if price < support * (1 + breakout_buffer) and rsi < rsi_low_threshold and trix > 0:
        print(f"🔄 BUY (Range, rebond support + TRIX) | Price={price:.4f} Support={support:.4f} RSI={rsi:.2f} TRIX={trix:.4f}")
        return "BUY"

    # Vente si proche de la résistance, RSI haut, et TRIX négatif (rejet)
    elif price > resistance * (1 - breakout_buffer) and rsi > rsi_high_threshold and trix < 0:
        print(f"🔄 SELL (Range, rejet resistance + TRIX) | Price={price:.4f} Resistance={resistance:.4f} RSI={rsi:.2f} TRIX={trix:.4f}")
        return "SELL"

    else:
        print(f"🔄 HOLD (Range) | Price={price:.4f} RSI={rsi:.2f} TRIX={trix:.4f}")
        return "HOLD"
