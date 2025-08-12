from indicators.combined_indicators import compute_all
import pandas as pd

def get_combined_signal(df, symbol):
    df = df.copy()
    df = compute_all(df, symbol=symbol)

    if len(df) < 50:  # besoin d'au moins 50 données pour EMA50
        return None, {}

    # Calcul EMA50
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Filtre tendance
    price_above_ema = last['close'] > last['ema50']
    price_below_ema = last['close'] < last['ema50']

    # Détection des signaux
    macd_buy = prev['macd'] < prev['signal'] and last['macd'] > last['signal']
    macd_sell = prev['macd'] > prev['signal'] and last['macd'] < last['signal']

    rsi_buy = last['rsi'] < 30
    rsi_sell = last['rsi'] > 70

    breakout_buy = last['close'] > df['high_breakout'][-20:-1].max()
    breakout_sell = last['close'] < df['low_breakout'][-20:-1].min()

    trix_buy = prev['trix'] < 0 and last['trix'] > 0
    trix_sell = prev['trix'] > 0 and last['trix'] < 0

    # Détermine le signal avec filtre EMA50
    if price_above_ema and macd_buy and rsi_buy and breakout_buy and trix_buy:
        signal = "BUY"
    elif price_below_ema and macd_sell and rsi_sell and breakout_sell and trix_sell:
        signal = "SELL"
    else:
        signal = None

    indicators = {
        "MACD": last['macd'],
        "MACD_signal": last['signal'],
        "RSI": last['rsi'],
        "TRIX": last['trix'],
        "HighBreakout": df['high_breakout'][-20:-1].max(),
        "LowBreakout": df['low_breakout'][-20:-1].min(),
        "Close": last['close'],
        "EMA50": last['ema50']
    }

    return signal, indicators
