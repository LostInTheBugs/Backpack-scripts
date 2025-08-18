# signals/three_out_of_four_conditions.py - Version simple
from indicators.combined_indicators import compute_all
from indicators.rsi_calculator import get_cached_rsi
from utils.logger import log
import pandas as pd

STOP_LOSS_PERCENT = 0.5
TAKE_PROFIT_PERCENT = 1.0

async def get_combined_signal(df, symbol, stop_loss_pct=None, take_profit_pct=None):
    df = df.copy()
    
    # 1. Calculer tous les indicateurs SAUF RSI
    df = await compute_all(df, symbol=symbol)
    
    # 2. APRÈS compute_all, récupérer et ÉCRASER le RSI avec la bonne valeur
    try:
        rsi_value = await get_cached_rsi(symbol, interval="5m")
        if rsi_value is not None:
            df['rsi'] = rsi_value  # ✅ Écraser le RSI de compute_all
            log(f"[{symbol}] 🎯 RSI écrasé avec valeur API: {rsi_value:.2f}", level="DEBUG")
        else:
            log(f"[{symbol}] ⚠️ RSI API indisponible, utilisation compute_all", level="ERROR")
    except Exception as e:
        print(f"[{symbol}] ❌ Erreur RSI API: {e}")

    if len(df) < 50:
        return None, {}

    # Calcul EMA50
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Le reste du code reste identique...
    price_above_ema = last['close'] > last['ema50']
    price_below_ema = last['close'] < last['ema50']

    macd_buy = prev['macd'] < prev['signal'] and last['macd'] > last['signal']
    macd_sell = prev['macd'] > prev['signal'] and last['macd'] < last['signal']

    rsi_buy = last['rsi'] < 50  # ✅ Utilisera le bon RSI
    rsi_sell = last['rsi'] > 50

    breakout_buy = last['close'] > df['high_breakout'][-20:-1].max()
    breakout_sell = last['close'] < df['low_breakout'][-20:-1].min()

    trix_buy = prev['trix'] < 0 and last['trix'] > 0
    trix_sell = prev['trix'] > 0 and last['trix'] < 0

    conditions_buy = [macd_buy, rsi_buy, breakout_buy, trix_buy]
    conditions_sell = [macd_sell, rsi_sell, breakout_sell, trix_sell]

    if price_above_ema and sum(conditions_buy) >= 3:
        signal = "BUY"
    elif price_below_ema and sum(conditions_sell) >= 3:
        signal = "SELL"
    else:
        signal = None

    indicators = {
        "MACD": last['macd'],
        "MACD_signal": last['signal'],
        "RSI": last['rsi'],  # ✅ Le RSI correct
        "TRIX": last['trix'],
        "HighBreakout": df['high_breakout'][-20:-1].max(),
        "LowBreakout": df['low_breakout'][-20:-1].min(),
        "Close": last['close'],
        "EMA50": last['ema50'],
        "ConditionsBUY_met": sum(conditions_buy),
        "ConditionsSELL_met": sum(conditions_sell),
        "StopLossPrice": last['close'] * (1 - STOP_LOSS_PERCENT / 100) if signal == "BUY" else last['close'] * (1 + STOP_LOSS_PERCENT / 100),
        "TakeProfitPrice": last['close'] * (1 + TAKE_PROFIT_PERCENT / 100) if signal == "BUY" else last['close'] * (1 - TAKE_PROFIT_PERCENT / 100),
    }

    return signal, indicators