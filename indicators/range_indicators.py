import pandas as pd
import ta

def compute_range_indicators(df):
    """
    Calcule les indicateurs nécessaires pour les stratégies Range et RangeSoft.
    Modifie le DataFrame en place.
    """
    if 'RSI' not in df.columns:
        df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

    if 'TRIX' not in df.columns:
        df['TRIX'] = ta.trend.trix(close=df['close'], window=15)

    if 'High20' not in df.columns:
        df['High20'] = df['high'].rolling(window=20).max()

    if 'Low20' not in df.columns:
        df['Low20'] = df['low'].rolling(window=20).min()

    return df