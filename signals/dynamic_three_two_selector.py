import pandas as pd
from signals.three_out_of_four_conditions import get_combined_signal as three_out_of_four
from signals.two_out_of_four_scalp import get_combined_signal as two_out_of_four
from utils.logger import log
from config.settings import get_strategy_config
from indicators.rsi_calculator import get_cached_rsi
import inspect

strategy_cfg = get_strategy_config()

def prepare_indicators(df, symbol=None):
    """Version synchrone pour rétro-compatibilité"""
    if symbol is None:
        log("[WARNING] ⚠️ Symbol manquant dans prepare_indicators, utilisation version simplifiée", level="WARNING")
        ema_short = 20
        ema_medium = 50  
        ema_long = 200
        
        df['EMA20'] = df['close'].ewm(span=ema_short).mean()
        df['EMA50'] = df['close'].ewm(span=ema_medium).mean()  
        df['EMA200'] = df['close'].ewm(span=ema_long).mean()
        df['RSI'] = 50.0
        return df
    
    return prepare_indicators_sync(df, symbol)

def prepare_indicators_sync(df, symbol):
    ema_short = strategy_cfg.ema_periods['short']
    ema_medium = strategy_cfg.ema_periods['medium']
    ema_long = strategy_cfg.ema_periods['long']

    df['EMA20'] = df['close'].ewm(span=ema_short).mean()
    df['EMA50'] = df['close'].ewm(span=ema_medium).mean()
    df['EMA200'] = df['close'].ewm(span=ema_long).mean()

    df['RSI'] = 50.0
    log(f"[WARNING] [{symbol}] ⚠️ RSI fixé à 50 (version sync)", level="WARNING")
    
    return df

async def detect_market_context(df, symbol):
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    
    rsi = await get_cached_rsi(symbol, interval="5m")
    log(f"[INFO] [{symbol}] [DEBUG] EMA20: {ema20:.4f}, EMA50: {ema50:.4f}, EMA200: {ema200:.4f}, RSI: {rsi:.2f}", level="INFO")

    if ema20 > ema50 and rsi > 50:
        return 'bull'
    elif ema20 < ema50 and rsi < 50:
        return 'bear'
    else:
        return 'range'

async def get_combined_signal(df, symbol):
    df = prepare_indicators(df, symbol)
    context = await detect_market_context(df, symbol)

    if context in ['bull', 'bear']:
        stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
        take_profit = strategy_cfg.three_out_of_four.take_profit_pct

        if inspect.iscoroutinefunction(three_out_of_four):
            signal, details = await three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
        else:
            signal, details = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)

    else:
        stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
        take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct

        if inspect.iscoroutinefunction(two_out_of_four):
            signal, details = await two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
        else:
            signal, details = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)

    return signal, details

def get_combined_signal_sync(df, symbol):
    df = prepare_indicators_sync(df, symbol)
    
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    rsi = 50.0

    if ema20 > ema50 and rsi > 50:
        context = 'bull'
    elif ema20 < ema50 and rsi < 50:
        context = 'bear'
    else:
        context = 'range'

    if context in ['bull', 'bear']:
        stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
        take_profit = strategy_cfg.three_out_of_four.take_profit_pct
        signal, details = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    else:
        stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
        take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct
        signal, details = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    
    return signal, details
