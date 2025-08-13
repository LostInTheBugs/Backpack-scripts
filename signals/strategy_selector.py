import pandas as pd
import ta
from utils.logger import log

def prepare_indicators(df):
    df['EMA20'] = df['close'].ewm(span=20).mean()
    df['EMA50'] = df['close'].ewm(span=50).mean()
    df['EMA200'] = df['close'].ewm(span=200).mean()

    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    macd = ta.trend.MACD(close=df['close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()

    df['TRIX'] = ta.trend.trix(close=df['close'], window=15)

    return df

def detect_market_context(df):
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    ema200 = df['EMA200'].iloc[-1]
    rsi = df['RSI'].iloc[-1]

    if ema20 > ema50 > ema200 and rsi > 55:
        return 'bull'
    elif ema20 < ema50 < ema200 and rsi < 45:
        return 'bear'
    else:
        return 'range'

def strategy_auto(df, mode='normal'):
    df = prepare_indicators(df)

    trix = df['TRIX'].iloc[-1]
    context = detect_market_context(df)

    price = df['close'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    macd = df['MACD'].iloc[-1]
    macd_signal = df['MACD_signal'].iloc[-1]
    high = df['high'].rolling(window=20).max().iloc[-1]
    low = df['low'].rolling(window=20).min().iloc[-1]

    # Seuils adaptatifs
    if mode == 'soft':
        breakout_thresh = 0.004  # 0.4% (vs 0.2%)
        trix_buy = 0.03
        trix_sell = -0.03
        rsi_buy = 50
        rsi_sell = 50
    else:
        breakout_thresh = 0.002
        trix_buy = 0.1
        trix_sell = -0.1
        rsi_buy = 55
        rsi_sell = 45

    context_info = (
        f"📊 Mode={mode} | Context={context} | Price={price:.4f} | High={high:.4f} | Low={low:.4f} | "
        f"RSI={rsi:.2f} | MACD={macd:.5f} | Signal={macd_signal:.5f} | TRIX={trix:.5f}"
    )

    if context == 'bull':
        if (price > high * (1 - breakout_thresh) and macd > macd_signal and rsi > rsi_buy) or (trix > trix_buy):
            log("[INFO] 🐂 BUY (Bull) | " + context_info, level="INFO")
            return 'BUY'
        else:
            log("[INFO] 🐂 HOLD (Bull) | " + context_info, level="INFO")
            return 'HOLD'

    elif context == 'bear':
        if (price < low * (1 + breakout_thresh) and macd < macd_signal and rsi < rsi_sell) or (trix < trix_sell):
            log("[INFO] 🐻 SELL (Bear) | " + context_info, level="INFO")
            return 'SELL'
        else:
            log("[INFO] 🐻 HOLD (Bear) | " + context_info, level="INFO")
            return 'HOLD'

    elif context == 'range':
        support = low
        resistance = high
        if price < support * 1.01 and rsi < 35 and trix > 0:
            log("🔄 BUY (Range) | " + context_info)
            return 'BUY'
        elif price > resistance * 0.99 and rsi > 65 and trix < 0:
            log("🔄 SELL (Range) | " + context_info)
            return 'SELL'
        else:
            log("🔄 HOLD (Range) | " + context_info)
            return 'HOLD'

    return 'HOLD'

def strategy_autosoft(df):
    return strategy_auto(df, mode='soft')

def get_strategy_for_market(df):
    """
    Retourne une stratégie recommandée selon le contexte détecté.
    """
    df = prepare_indicators(df)
    context = detect_market_context(df)

    if context == 'bull':
        strategy = "Trix"
    elif context == 'bear':
        strategy = "Breakout"
    else:
        strategy = "Range"  # recommandé en range

    return context, strategy
