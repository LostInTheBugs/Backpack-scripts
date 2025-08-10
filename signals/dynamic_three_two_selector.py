import pandas as pd
import ta
from signals.three_out_of_four_conditions import get_combined_signal as three_out_of_four
from signals.two_out_of_four_scalp import get_combined_signal as two_out_of_four
from utils.logger import log
from config.settings import get_strategy_config

strategy_cfg = get_strategy_config()

def prepare_indicators(df):
    # Utiliser les périodes dans la config
    ema_short = strategy_cfg.ema_periods['short']
    ema_medium = strategy_cfg.ema_periods['medium']
    ema_long = strategy_cfg.ema_periods['long']
    rsi_period = strategy_cfg.rsi_period

    df['EMA20'] = df['close'].ewm(span=ema_short).mean()
    df['EMA50'] = df['close'].ewm(span=ema_medium).mean()
    df['EMA200'] = df['close'].ewm(span=ema_long).mean()

    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=rsi_period).rsi()
    return df

def detect_market_context(df):
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    rsi = df['RSI'].iloc[-1]

    # Tu peux ajuster ces seuils dans la config si tu veux plus tard
    if ema20 > ema50 > ema200 and rsi > 55:
        return 'bull'
    elif ema20 < ema50 < ema200 and rsi < 45:
        return 'bear'
    else:
        return 'range'

def get_combined_signal(df):
    df = prepare_indicators(df)
    context = detect_market_context(df)

    if context in ['bull', 'bear']:
        log(f"📈 Contexte = {context.upper()} → Stratégie = ThreeOutOfFour")
        return three_out_of_four(df)
    else:
        log(f"🔄 Contexte = RANGE → Stratégie = TwoOutOfFourScalp")
        return two_out_of_four(df)
