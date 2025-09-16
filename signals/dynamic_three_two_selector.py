# signal/dynamic_three_two_selector_optimized.py
from signals.three_out_of_four_conditions import get_combined_signal as three_out_of_four
from signals.two_out_of_four_scalp import get_combined_signal as two_out_of_four
from utils.logger import log
from config.settings import get_strategy_config
from indicators.rsi_calculator import get_cached_rsi
import inspect
import numpy as np

strategy_cfg = get_strategy_config()

# Cache pour éviter les changements de contexte trop fréquents
_context_cache = {}
_context_history = {}

def calculate_rsi_fallback(df, period=14):
    """Calcule un RSI de fallback basé sur les prix si l'API est indisponible"""
    if len(df) < period + 1:
        return 50.0
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50.0

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
        df['RSI'] = calculate_rsi_fallback(df)
        return df
    
    return prepare_indicators_sync(df, symbol)

def prepare_indicators_sync(df, symbol):
    """Prépare les indicateurs EMA et RSI avec fallback amélioré."""
    ema_short = strategy_cfg.ema_periods['short']
    ema_medium = strategy_cfg.ema_periods['medium']
    ema_long = strategy_cfg.ema_periods['long']

    df['EMA20'] = df['close'].ewm(span=ema_short).mean()
    df['EMA50'] = df['close'].ewm(span=ema_medium).mean()
    df['EMA200'] = df['close'].ewm(span=ema_long).mean()

    # --- RSI handling amélioré ---
    rsi_value = None
    try:
        if not inspect.iscoroutinefunction(get_cached_rsi):
            rsi_value = get_cached_rsi(symbol, interval="5m")
            if rsi_value is not None and 0 <= rsi_value <= 100:
                df['RSI'] = rsi_value
                log(f"[{symbol}] ✅ RSI API récupéré: {rsi_value:.2f}", level="DEBUG")
            else:
                rsi_value = None
    except Exception as e:
        log(f"[{symbol}] ⚠️ Erreur récupération RSI API: {e}", level="WARNING")

    # Fallback amélioré avec calcul RSI
    if rsi_value is None:
        rsi_fallback = calculate_rsi_fallback(df)
        df['RSI'] = rsi_fallback
        log(f"[{symbol}] 📊 RSI calculé localement: {rsi_fallback:.2f}", level="INFO")
    
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
    
    return df

def get_ema_trend_strength(ema20, ema50, ema200):
    """Calcule la force de la tendance basée sur la séparation des EMAs"""
    short_med_diff = abs(ema20 - ema50) / ema50
    med_long_diff = abs(ema50 - ema200) / ema200
    
    # Tendance forte si les EMAs sont bien séparées
    return (short_med_diff + med_long_diff) / 2

async def detect_market_context(df, symbol):
    """Détection de contexte améliorée avec hysteresis et confirmation multi-timeframe"""
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    
    # Récupérer RSI avec fallback intelligent
    try:
        rsi = await get_cached_rsi(symbol, interval="5m")
        if rsi is None or not (0 <= rsi <= 100):
            rsi = calculate_rsi_fallback(df)
            log(f"[{symbol}] 📊 RSI calculé localement pour contexte: {rsi:.2f}", level="INFO")
        else:
            log(f"[{symbol}] ✅ RSI API pour contexte: {rsi:.2f}", level="DEBUG")
    except Exception as e:
        rsi = calculate_rsi_fallback(df)
        log(f"[{symbol}] ⚠️ Erreur RSI contexte, calcul local: {e}", level="WARNING")
    
    # Calcul de la force de tendance
    trend_strength = get_ema_trend_strength(ema20, ema50, ema200)
    
    # Récupération du contexte précédent pour hysteresis
    previous_context = _context_cache.get(symbol, 'range')
    
    # Seuils adaptatifs avec hysteresis pour éviter le flip-flop
    if previous_context == 'bull':
        bull_ema_threshold = 0.998  # Plus dur de sortir du bull
        bull_rsi_threshold = 45     # RSI threshold plus bas pour rester bull
    else:
        bull_ema_threshold = 1.002  # Plus facile d'entrer en bull
        bull_rsi_threshold = 55     # RSI threshold plus haut pour entrer bull
    
    if previous_context == 'bear':
        bear_ema_threshold = 1.002  # Plus dur de sortir du bear
        bear_rsi_threshold = 55     # RSI threshold plus haut pour rester bear
    else:
        bear_ema_threshold = 0.998  # Plus facile d'entrer en bear
        bear_rsi_threshold = 45     # RSI threshold plus bas pour entrer bear
    
    # Détection avec confirmation de force de tendance
    context = 'range'  # Default
    
    if (ema20 > ema50 * bull_ema_threshold and 
        rsi > bull_rsi_threshold and 
        trend_strength > 0.01):  # Minimum 1% de séparation EMA
        context = 'bull'
    elif (ema20 < ema50 * bear_ema_threshold and 
          rsi < bear_rsi_threshold and 
          trend_strength > 0.01):
        context = 'bear'
    else:
        context = 'range'
    
    # Historique pour validation (évite les changements trop rapides)
    if symbol not in _context_history:
        _context_history[symbol] = []
    
    _context_history[symbol].append(context)
    if len(_context_history[symbol]) > 3:
        _context_history[symbol] = _context_history[symbol][-3:]
    
    # Confirmation: changement uniquement si 2/3 dernières détections concordent
    if len(_context_history[symbol]) >= 2:
        recent_contexts = _context_history[symbol][-2:]
        if previous_context != context:
            # Changement demandé - vérifier confirmation
            if recent_contexts.count(context) < 2:
                context = previous_context  # Garder l'ancien contexte
                log(f"[{symbol}] 🔄 Changement contexte rejeté par confirmation. Garde: {context}", level="DEBUG")
    
    # Mise à jour du cache
    _context_cache[symbol] = context
    
    log(f"[{symbol}] 📈 EMA20: {ema20:.4f}, EMA50: {ema50:.4f}, EMA200: {ema200:.4f}, RSI: {rsi:.2f}, Tendance: {trend_strength:.3f}, Contexte: {context}", level="DEBUG")

    return context

async def get_combined_signal(df, symbol):
    """Signal combiné optimisé avec gestion d'erreurs améliorée"""
    # Préparation des indicateurs
    df = prepare_indicators_clean(df, symbol)
    
    # Détection du contexte avec hysteresis
    context = await detect_market_context(df, symbol)

    try:
        if context in ['bull', 'bear']:
            # Marché en tendance - stratégie conservative
            stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
            take_profit = strategy_cfg.three_out_of_four.take_profit_pct

            if inspect.iscoroutinefunction(three_out_of_four):
                signal, details = await three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
            else:
                signal, details = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
            
            log(f"[{symbol}] 📊 Stratégie TREND utilisée - Context: {context}", level="DEBUG")

        else:
            # Marché en range - stratégie scalping
            stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
            take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct

            if inspect.iscoroutinefunction(two_out_of_four):
                signal, details = await two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
            else:
                signal, details = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
            
            log(f"[{symbol}] 🎯 Stratégie SCALP utilisée - Context: {context}", level="DEBUG")
    
    except Exception as e:
        log(f"[{symbol}] ❌ Erreur dans get_combined_signal: {e}", level="ERROR")
        return 'HOLD', {'error': str(e), 'context': context}

    # Ajout du contexte aux détails
    if isinstance(details, dict):
        details['market_context'] = context
    
    return signal, details

def get_combined_signal_sync(df, symbol):
    """Version synchrone optimisée avec les mêmes améliorations"""
    df = prepare_indicators_sync(df, symbol)
    
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]

    # RSI handling synchrone amélioré
    rsi_value = None
    try:
        if not inspect.iscoroutinefunction(get_cached_rsi):
            rsi_value = get_cached_rsi(symbol, interval="5m")
            if rsi_value is not None and 0 <= rsi_value <= 100:
                log(f"[{symbol}] ✅ RSI API sync: {rsi_value:.2f}", level="DEBUG")
            else:
                rsi_value = None
    except Exception as e:
        log(f"[{symbol}] ⚠️ Erreur récupération RSI sync: {e}", level="WARNING")

    # Fallback intelligent
    rsi = rsi_value if rsi_value is not None else calculate_rsi_fallback(df)
    if rsi_value is None:
        log(f"[{symbol}] 📊 RSI calculé localement sync: {rsi:.2f}", level="INFO")

    # Détection contexte avec hysteresis (version sync)
    trend_strength = get_ema_trend_strength(ema20, ema50, ema200)
    previous_context = _context_cache.get(symbol, 'range')
    
    # Seuils adaptatifs identiques à la version async
    if previous_context == 'bull':
        bull_ema_threshold = 0.998
        bull_rsi_threshold = 45
    else:
        bull_ema_threshold = 1.002
        bull_rsi_threshold = 55
    
    if previous_context == 'bear':
        bear_ema_threshold = 1.002
        bear_rsi_threshold = 55
    else:
        bear_ema_threshold = 0.998
        bear_rsi_threshold = 45

    # Détection de contexte
    if (ema20 > ema50 * bull_ema_threshold and 
        rsi > bull_rsi_threshold and 
        trend_strength > 0.01):
        context = 'bull'
    elif (ema20 < ema50 * bear_ema_threshold and 
          rsi < bear_rsi_threshold and 
          trend_strength > 0.01):
        context = 'bear'
    else:
        context = 'range'

    # Mise à jour cache
    _context_cache[symbol] = context

    # Application de la stratégie
    try:
        if context in ['bull', 'bear']:
            stop_loss = strategy_cfg.three_out_of_four.stop_loss_pct
            take_profit = strategy_cfg.three_out_of_four.take_profit_pct
            signal, details = three_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
        else:
            stop_loss = strategy_cfg.two_out_of_four_scalp.stop_loss_pct
            take_profit = strategy_cfg.two_out_of_four_scalp.take_profit_pct
            signal, details = two_out_of_four(df, symbol, stop_loss_pct=stop_loss, take_profit_pct=take_profit)
        
        # Ajout contexte aux détails
        if isinstance(details, dict):
            details['market_context'] = context
            details['trend_strength'] = trend_strength
    
    except Exception as e:
        log(f"[{symbol}] ❌ Erreur dans get_combined_signal_sync: {e}", level="ERROR")
        return 'HOLD', {'error': str(e), 'context': context}
    
    return signal, details

def reset_context_cache():
    """Fonction utilitaire pour reset le cache (utile pour les tests ou redémarrages)"""
    global _context_cache, _context_history
    _context_cache.clear()
    _context_history.clear()
    log("🔄 Cache de contexte réinitialisé", level="INFO")

def get_context_stats():
    """Retourne les statistiques du cache de contexte pour monitoring"""
    return {
        'cached_symbols': len(_context_cache),
        'contexts': dict(_context_cache),
        'history_length': {k: len(v) for k, v in _context_history.items()}
    }
