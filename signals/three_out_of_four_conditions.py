from indicators.combined_indicators import compute_all
import pandas as pd

def get_combined_signal(df, stop_loss_pct=None, take_profit_pct=None):
    df = df.copy()
    df = compute_all(df)

    if len(df) < 50:  # besoin d'assez de données pour EMA50
        return None, {}

    # Calcul EMA50
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Filtre tendance
    price_above_ema = last['close'] > last['ema50']
    price_below_ema = last['close'] < last['ema50']

    # Conditions assouplies
    macd_buy = prev['macd'] < prev['signal'] and last['macd'] > last['signal']
    macd_sell = prev['macd'] > prev['signal'] and last['macd'] < last['signal']

    rsi_buy = last['rsi'] < 50
    rsi_sell = last['rsi'] > 50

    breakout_buy = last['close'] > df['high_breakout'][-20:-1].max()
    breakout_sell = last['close'] < df['low_breakout'][-20:-1].min()

    trix_buy = prev['trix'] < 0 and last['trix'] > 0
    trix_sell = prev['trix'] > 0 and last['trix'] < 0

    # Vérifie combien de conditions sont vraies
    conditions_buy = [macd_buy, rsi_buy, breakout_buy, trix_buy]
    conditions_sell = [macd_sell, rsi_sell, breakout_sell, trix_sell]

    if price_above_ema and sum(conditions_buy) >= 3:
        signal = "BUY"
    elif price_below_ema and sum(conditions_sell) >= 3:
        signal = "SELL"
    else:
        signal = None

    # Retour des indicateurs pour debug
    indicators = {
        "MACD": last['macd'],
        "MACD_signal": last['signal'],
        "RSI": last['rsi'],
        "TRIX": last['trix'],
        "HighBreakout": df['high_breakout'][-20:-1].max(),
        "LowBreakout": df['low_breakout'][-20:-1].min(),
        "Close": last['close'],
        "EMA50": last['ema50'],
        "ConditionsBUY_met": sum(conditions_buy),
        "ConditionsSELL_met": sum(conditions_sell)
    }

    return signal, indicators
