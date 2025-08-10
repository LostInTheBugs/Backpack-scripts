# signals/dynamic_three_two_selector.py

import pandas as pd
import ta
from signals.three_out_of_four_conditions import get_combined_signal as three_out_of_four
from signals.two_out_of_four_scalp import get_combined_signal as two_out_of_four
from utils.logger import log

def prepare_indicators(df):
    df['EMA20'] = df['close'].ewm(span=20).mean()
    df['EMA50'] = df['close'].ewm(span=50).mean()
    df['EMA200'] = df['close'].ewm(span=200).mean()

    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    return df

def detect_market_context(df):
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    rsi = df['RSI'].iloc[-1]

    if ema20 > ema50 > ema200 and rsi > 55:
        return 'bull'
    elif ema20 < ema50 < ema200 and rsi < 45:
        return 'bear'
    else:
        return 'range'

def get_combined_signal(df):
    """
    Sélecteur dynamique :
    - Bull / Bear => ThreeOutOfFour
    - Range => TwoOutOfFourScalp
    """
    df = prepare_indicators(df)
    context = detect_market_context(df)

    if context in ["bull", "bear"]:
        log(f"📈 Contexte = {context.upper()} → Stratégie = ThreeOutOfFour")
        return three_out_of_four(df)
    else:
        log(f"🔄 Contexte = RANGE → Stratégie = TwoOutOfFourScalp")
        return two_out_of_four(df)
