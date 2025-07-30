import pandas as pd
import ta

def prepare_indicators(df):
    """
    Ajoute les indicateurs techniques nécessaires au DataFrame.
    """
    df['EMA20'] = df['close'].ewm(span=20).mean()
    df['EMA50'] = df['close'].ewm(span=50).mean()
    df['EMA200'] = df['close'].ewm(span=200).mean()

    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    macd = ta.trend.MACD(close=df['close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()

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

def strategy_auto(df):
    df = prepare_indicators(df)
    context = detect_market_context(df)

    price = df['close'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    macd = df['MACD'].iloc[-1]
    macd_signal = df['MACD_signal'].iloc[-1]
    high = df['high'].rolling(window=20).max().iloc[-1]
    low = df['low'].rolling(window=20).min().iloc[-1]

    breakout_thresh = 0.002  # 0.2% de tolérance
    context_info = f"📊 Contexte={context} | Price={price:.4f} | High={high:.4f} | Low={low:.4f} | RSI={rsi:.2f} | MACD={macd:.5f} | Signal={macd_signal:.5f}"

    if context == 'bull':
        if price > high * (1 - breakout_thresh) and macd > macd_signal and rsi > 55:
            print("🐂 Signal Bull: BUY | " + context_info)
            return 'BUY'
        else:
            print("🐂 Bull mais conditions insuffisantes | " + context_info)
            return 'HOLD'

    elif context == 'bear':
        if price < low * (1 + breakout_thresh) and macd < macd_signal and rsi < 45:
            print("🐻 Signal Bear: SELL | " + context_info)
            return 'SELL'
        else:
            print("🐻 Bear mais conditions insuffisantes | " + context_info)
            return 'HOLD'

    elif context == 'range':
        support = low
        resistance = high
        if price < support * 1.01 and rsi < 35:
            print("🔄 Range: BUY (rebond bas) | " + context_info)
            return 'BUY'
        elif price > resistance * 0.99 and rsi > 65:
            print("🔄 Range: SELL (rebond haut) | " + context_info)
            return 'SELL'
        else:
            print("🔄 Range: HOLD | " + context_info)
            return 'HOLD'

    return 'HOLD'


def get_strategy_for_market(df):
    """
    Retourne une stratégie recommandée selon le contexte détecté.
    """
    df = prepare_indicators(df)
    context = detect_market_context(df)

    if context == 'bull':
        strategy = "Trix"       # ou ta stratégie préférée en bull
    elif context == 'bear':
        strategy = "Breakout"   # par ex. stratégie breakout agressive
    else:
        strategy = "Combo"      # mélange pour les marchés en range

    return context, strategy