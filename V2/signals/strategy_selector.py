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

    # Ajout TRIX
    df['TRIX'] = ta.trend.trix(close=df['close'], window=15)
    trix = df['TRIX'].iloc[-1]

    context = detect_market_context(df)

    price = df['close'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    macd = df['MACD'].iloc[-1]
    macd_signal = df['MACD_signal'].iloc[-1]
    high = df['high'].rolling(window=20).max().iloc[-1]
    low = df['low'].rolling(window=20).min().iloc[-1]

    breakout_thresh = 0.002  # 0.2%
    context_info = (
        f"📊 Context={context} | Price={price:.4f} | High={high:.4f} | Low={low:.4f} | "
        f"RSI={rsi:.2f} | MACD={macd:.5f} | Signal={macd_signal:.5f} | TRIX={trix:.5f}"
    )

    # --- BULL ---
    if context == 'bull':
        if (
            (price > high * (1 - breakout_thresh) and macd > macd_signal and rsi > 55)
            or (trix > 0.1)
        ):
            print("🐂 BUY (Bull Market) | " + context_info)
            return 'BUY'
        else:
            print("🐂 HOLD (Bull) | " + context_info)
            return 'HOLD'

    # --- BEAR ---
    elif context == 'bear':
        if (
            (price < low * (1 + breakout_thresh) and macd < macd_signal and rsi < 45)
            or (trix < -0.1)
        ):
            print("🐻 SELL (Bear Market) | " + context_info)
            return 'SELL'
        else:
            print("🐻 HOLD (Bear) | " + context_info)
            return 'HOLD'

    # --- RANGE ---
    elif context == 'range':
        support = low
        resistance = high
        if price < support * 1.01 and rsi < 35 and trix > 0:
            print("🔄 BUY (Range, rebond bas + TRIX) | " + context_info)
            return 'BUY'
        elif price > resistance * 0.99 and rsi > 65 and trix < 0:
            print("🔄 SELL (Range, rebond haut + TRIX) | " + context_info)
            return 'SELL'
        else:
            print("🔄 HOLD (Range) | " + context_info)
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