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
    
    # Debug pour voir les valeurs actuelles
    log(f"[DEBUG] EMA20: {ema20:.4f}, EMA50: {ema50:.4f}, EMA200: {ema200:.4f}, RSI: {rsi:.2f}")

    # Conditions assouplies
    if ema20 > ema50 and rsi > 50:  # Pas besoin que EMA50 > EMA200
        log(f"[DEBUG] Context: BULL (EMA20 > EMA50 and RSI > 50)")
        return 'bull'
    elif ema20 < ema50 and rsi < 50:  # Pas besoin que EMA50 < EMA200
        log(f"[DEBUG] Context: BEAR (EMA20 < EMA50 and RSI < 50)")
        return 'bear'
    else:
        log(f"[DEBUG] Context: RANGE")
        return 'range'

def get_combined_signal(df, symbol):
    log(f"[DEBUG] DataFrame length before indicators: {len(df)}", level="DEBUG")
    log(f"[DEBUG] Any NaN in close? {df['close'].isna().any()}", level="DEBUG")
    df = prepare_indicators(df)
    context = detect_market_context(df)
    
    log(f"[DEBUG] Market context detected: {context}")

    if context in ['bull', 'bear']:
        stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
        take_profit = strategy_cfg.three_out_of_four.take_profit_pct
        log(f"📈 Using ThreeOutOfFour | Context: {context} | SL={stop_loss}% TP={take_profit}%")
        signal = three_out_of_four(df, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    else:
        stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
        take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct
        log(f"🔄 Using TwoOutOfFourScalp | Context: {context} | SL={stop_loss}% TP={take_profit}%")
        signal = two_out_of_four(df, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    
    log(f"[DEBUG] Final signal: {signal}")
    return signal