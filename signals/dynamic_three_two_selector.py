# signals/dynamic_three_two_selector.py (version modifiée)
import pandas as pd
import ta
from signals.three_out_of_four_conditions import get_combined_signal as three_out_of_four
from signals.two_out_of_four_scalp import get_combined_signal as two_out_of_four
from utils.logger import log
from config.settings import get_strategy_config
from indicators.rsi_calculator import get_cached_rsi

strategy_cfg = get_strategy_config()

def prepare_indicators(df, symbol=None):
    """Version synchrone pour rétro-compatibilité"""
    if symbol is None:
        log("⚠️ Symbol manquant dans prepare_indicators, utilisation version simplifiée", level="WARNING")
        # Version basique sans RSI API
        ema_short = 20
        ema_medium = 50  
        ema_long = 200
        
        df['EMA20'] = df['close'].ewm(span=ema_short).mean()
        df['EMA50'] = df['close'].ewm(span=ema_medium).mean()  
        df['EMA200'] = df['close'].ewm(span=ema_long).mean()
        df['RSI'] = 50.0  # Valeur neutre
        return df
    
    return prepare_indicators_sync(df, symbol)

def prepare_indicators_sync(df, symbol):
    """Version synchrone pour compatibilité"""
    ema_short = strategy_cfg.ema_periods['short']
    ema_medium = strategy_cfg.ema_periods['medium']
    ema_long = strategy_cfg.ema_periods['long']

    df['EMA20'] = df['close'].ewm(span=ema_short).mean()
    df['EMA50'] = df['close'].ewm(span=ema_medium).mean()
    df['EMA200'] = df['close'].ewm(span=ema_long).mean()

    # RSI fixe à 50 pour la version sync (fallback)
    df['RSI'] = 50.0
    log(f"[{symbol}] ⚠️ RSI fixé à 50 (version sync)")
    
    return df

async def detect_market_context(df, symbol):
    """Version asynchrone pour la détection de contexte"""
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    
    # RSI depuis l'API
    rsi = await get_cached_rsi(symbol, interval="5m")
    
    # Debug pour voir les valeurs actuelles
    log(f"[{symbol}] [DEBUG] EMA20: {ema20:.4f}, EMA50: {ema50:.4f}, EMA200: {ema200:.4f}, RSI: {rsi:.2f}")

    # Conditions assouplies
    if ema20 > ema50 and rsi > 50:  # Pas besoin que EMA50 > EMA200
        log(f"[{symbol}] [DEBUG] Context: BULL (EMA20 > EMA50 and RSI > 50)")
        return 'bull'
    elif ema20 < ema50 and rsi < 50:  # Pas besoin que EMA50 < EMA200
        log(f"[{symbol}] [DEBUG] Context: BEAR (EMA20 < EMA50 and RSI < 50)")
        return 'bear'
    else:
        log(f"[{symbol}] [DEBUG] Context: RANGE")
        return 'range'

async def get_combined_signal(df, symbol):
    """Version asynchrone du signal combiné"""
    log(f"[{symbol}] [DEBUG] DataFrame length before indicators: {len(df)}", level="DEBUG")
    log(f"[{symbol}] [DEBUG] Any NaN in close? {df['close'].isna().any()}", level="DEBUG")
    
    df = await prepare_indicators(df, symbol)
    context = await detect_market_context(df, symbol)
    
    log(f"[{symbol}] [DEBUG] Market context detected: {context}")

    if context in ['bull', 'bear']:
        stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
        take_profit = strategy_cfg.three_out_of_four.take_profit_pct
        log(f"[{symbol}] 📈 Using ThreeOutOfFour | Context: {context} | SL={stop_loss}% TP={take_profit}%")
        signal = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    else:
        stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
        take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct
        log(f"[{symbol}] 🔄 Using TwoOutOfFourScalp | Context: {context} | SL={stop_loss}% TP={take_profit}%")
        signal = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    
    log(f"[{symbol}] [DEBUG] Final signal: {signal}")
    return signal

def get_combined_signal_sync(df, symbol):
    """Version synchrone pour compatibilité"""
    df = prepare_indicators_sync(df, symbol)
    
    # Détection de contexte simplifiée
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    rsi = 50.0  # RSI fixe
    
    if ema20 > ema50 and rsi > 50:
        context = 'bull'
    elif ema20 < ema50 and rsi < 50:
        context = 'bear'
    else:
        context = 'range'

    log(f"[{symbol}] [DEBUG] Market context detected (sync): {context}")

    if context in ['bull', 'bear']:
        stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
        take_profit = strategy_cfg.three_out_of_four.take_profit_pct
        signal = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    else:
        stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
        take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct
        signal = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    
    return signal