from indicators.combined_indicators import compute_all
import asyncio
import pandas as pd

async def get_combined_signal(df, symbol):
    """
    Version async qui gère correctement compute_all
    """
    if df.empty or len(df) < 50:
        return "HOLD"

    try:
        # Appel de compute_all avec await si c'est une coroutine
        result = compute_all(df, symbol=symbol)
        
        if asyncio.iscoroutine(result):
            df = await result
        else:
            df = result
        
    except Exception as e:
        from utils.logger import log
        log(f"[ERROR] [{symbol}] Error in compute_all: {e}", level="ERROR")
        return "HOLD"

    # Vérification que compute_all a bien retourné un DataFrame
    if not isinstance(df, pd.DataFrame):
        from utils.logger import log
        log(f"[ERROR] [{symbol}] compute_all returned {type(df)} instead of DataFrame", level="ERROR")
        return "HOLD"

    if df.empty:
        from utils.logger import log
        log(f"[WARNING] [{symbol}] compute_all returned empty DataFrame", level="WARNING")
        return "HOLD"

    # Vérification des colonnes nécessaires
    required_columns = ['close', 'macd', 'signal', 'rsi', 'high_breakout', 'low_breakout', 'high']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        from utils.logger import log
        log(f"[WARNING] [{symbol}] Missing columns after compute_all: {missing_columns}", level="WARNING")
        return "HOLD"

    try:
        close = df['close']
        macd_hist = df['macd'] - df['signal']
        rsi_val = df['rsi'].iloc[-1]
        highest_high = df['high_breakout']
        lowest_low = df['low_breakout']
        last_close = close.iloc[-1]

        macd_bull = macd_hist.iloc[-1] > 0
        macd_bear = macd_hist.iloc[-1] < 0

        rsi_oversold = rsi_val < 30
        rsi_overbought = rsi_val > 70

        breakout_up = last_close > highest_high.iloc[-2] if len(highest_high) > 1 else False
        breakout_down = last_close < lowest_low.iloc[-2] if len(lowest_low) > 1 else False

        if macd_bull and rsi_oversold and breakout_up:
            return "BUY"
        elif macd_bear and rsi_overbought and breakout_down:
            return "SELL"
        else:
            return "HOLD"

    except Exception as e:
        from utils.logger import log
        log(f"[ERROR] [{symbol}] Error processing signal: {e}", level="ERROR")
        return "HOLD"

def get_combined_signal_sync(df, symbol):
    """
    Version synchrone de sauvegarde qui utilise asyncio.run() si nécessaire
    """
    if df.empty or len(df) < 50:
        return "HOLD"

    try:
        # Appel de compute_all
        result = compute_all(df, symbol=symbol)
        
        # Si c'est une coroutine, on utilise asyncio.run
        if asyncio.iscoroutine(result):
            try:
                df = asyncio.run(result)
            except RuntimeError:
                # Si on est déjà dans un event loop
                from utils.logger import log
                log(f"[ERROR] [{symbol}] Cannot run async compute_all from sync context in existing event loop", level="ERROR")
                return "HOLD"
        else:
            df = result
        
    except Exception as e:
        from utils.logger import log
        log(f"[ERROR] [{symbol}] Error in compute_all: {e}", level="ERROR")
        return "HOLD"

    # Vérification que compute_all a bien retourné un DataFrame
    if not isinstance(df, pd.DataFrame):
        from utils.logger import log
        log(f"[ERROR] [{symbol}] compute_all returned {type(df)} instead of DataFrame", level="ERROR")
        return "HOLD"

    if df.empty:
        from utils.logger import log
        log(f"[WARNING] [{symbol}] compute_all returned empty DataFrame", level="WARNING")
        return "HOLD"

    # Vérification des colonnes nécessaires
    required_columns = ['close', 'macd', 'signal', 'rsi', 'high_breakout', 'low_breakout', 'high']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        from utils.logger import log
        log(f"[WARNING] [{symbol}] Missing columns after compute_all: {missing_columns}", level="WARNING")
        return "HOLD"

    try:
        close = df['close']
        macd_hist = df['macd'] - df['signal']
        rsi_val = df['rsi'].iloc[-1]
        highest_high = df['high_breakout']
        lowest_low = df['low_breakout']
        last_close = close.iloc[-1]

        macd_bull = macd_hist.iloc[-1] > 0
        macd_bear = macd_hist.iloc[-1] < 0

        rsi_oversold = rsi_val < 30
        rsi_overbought = rsi_val > 70

        breakout_up = last_close > highest_high.iloc[-2] if len(highest_high) > 1 else False
        breakout_down = last_close < lowest_low.iloc[-2] if len(lowest_low) > 1 else False

        if macd_bull and rsi_oversold and breakout_up:
            return "BUY"
        elif macd_bear and rsi_overbought and breakout_down:
            return "SELL"
        else:
            return "HOLD"

    except Exception as e:
        from utils.logger import log
        log(f"[ERROR] [{symbol}] Error processing signal: {e}", level="ERROR")
        return "HOLD"