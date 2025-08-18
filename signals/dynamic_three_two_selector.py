# signal/dynamic_three_two_selector.py
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
        log("⚠️ Symbol manquant dans prepare_indicators, utilisation version simplifiée", level="WARNING")
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
    """Prépare les indicateurs EMA et RSI (fallback à 50 uniquement si nécessaire)."""
    ema_short = strategy_cfg.ema_periods['short']
    ema_medium = strategy_cfg.ema_periods['medium']
    ema_long = strategy_cfg.ema_periods['long']

    df['EMA20'] = df['close'].ewm(span=ema_short).mean()
    df['EMA50'] = df['close'].ewm(span=ema_medium).mean()
    df['EMA200'] = df['close'].ewm(span=ema_long).mean()

    # --- RSI handling ---
    rsi_value = None
    try:
        # get_cached_rsi peut être async → on ne l'utilise que si c'est synchrone
        if not inspect.iscoroutinefunction(get_cached_rsi):
            rsi_value = get_cached_rsi(symbol, interval="5m")
            if rsi_value is not None:
                df['RSI'] = rsi_value
                log(f"[{symbol}] ✅ RSI récupéré en sync: {rsi_value:.2f}", level="INFO")
    except Exception as e:
        log(f"[{symbol}] ⚠️ Erreur récupération RSI sync: {e}", level="WARNING")

    # fallback si pas de RSI dispo
    if rsi_value is None:
        df['RSI'] = 50.0
        log(f"[{symbol}] ⚠️ RSI fixé à 50 (fallback sync)", level="WARNING")
    
    return df

def prepare_indicators_clean(df, symbol=None):
    """Version propre sans RSI - seulement EMA"""
    if symbol is None:
        log("⚠️ Symbol manquant dans prepare_indicators_clean", level="WARNING")
        ema_short = 20
        ema_medium = 50  
        ema_long = 200
    else:
        ema_short = strategy_cfg.ema_periods['short']
        ema_medium = strategy_cfg.ema_periods['medium']
        ema_long = strategy_cfg.ema_periods['long']
        
    df['EMA20'] = df['close'].ewm(span=ema_short).mean()
    df['EMA50'] = df['close'].ewm(span=ema_medium).mean()  
    df['EMA200'] = df['close'].ewm(span=ema_long).mean()
    
    # ✅ Pas de RSI ici - sera géré dans detect_market_context
    return df

async def detect_market_context(df, symbol):
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    
    # ✅ Récupérer le bon RSI via API
    try:
        rsi = await get_cached_rsi(symbol, interval="5m")
        if rsi is None:
            rsi = 50.0
            log(f"[{symbol}] ⚠️ RSI API indisponible, fallback à 50 pour contexte", level="WARNING")
        else:
            log(f"[{symbol}] ✅ RSI contexte récupéré: {rsi:.2f}", level="INFO")
    except Exception as e:
        rsi = 50.0
        log(f"[{symbol}] ⚠️ Erreur RSI contexte: {e}, fallback à 50", level="WARNING")
    
    log(f"[{symbol}]EMA20: {ema20:.4f}, EMA50: {ema50:.4f}, EMA200: {ema200:.4f}, RSI: {rsi:.2f}", level="DEBUG")

    if ema20 > ema50 and rsi > 50:
        return 'bull'
    elif ema20 < ema50 and rsi < 50:
        return 'bear'
    else:
        return 'range'

async def get_combined_signal(df, symbol):
    # ✅ Préparer seulement les EMA (sans RSI)
    df = prepare_indicators_clean(df, symbol)
    
    # ✅ detect_market_context récupère son propre RSI
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
    """Version synchrone - garde l'ancienne logique pour compatibilité"""
    df = prepare_indicators_sync(df, symbol)
    
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]

    # --- RSI handling synchrone ---
    rsi_value = None
    try:
        if not inspect.iscoroutinefunction(get_cached_rsi):
            rsi_value = get_cached_rsi(symbol, interval="5m")
            if rsi_value is not None:
                log(f"[{symbol}] ✅ RSI utilisé en sync: {rsi_value:.2f}", level="INFO")
    except Exception as e:
        log(f"[{symbol}] ⚠️ Erreur récupération RSI sync: {e}", level="WARNING")

    # fallback si pas dispo
    rsi = rsi_value if rsi_value is not None else 50.0
    if rsi_value is None:
        log(f"[{symbol}] ⚠️ RSI fixé à 50 (fallback sync dans get_combined_signal_sync)", level="WARNING")

    # --- Détection du contexte ---
    if ema20 > ema50 and rsi > 50:
        context = 'bull'
    elif ema20 < ema50 and rsi < 50:
        context = 'bear'
    else:
        context = 'range'

    # --- Application stratégie ---
    if context in ['bull', 'bear']:
        stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
        take_profit = strategy_cfg.three_out_of_four.take_profit_pct
        signal, details = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    else:
        stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
        take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct
        signal, details = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
    
    return signal, details