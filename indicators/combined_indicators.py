import pandas as pd
from utils.logger import log

def calculate_macd(df, fast=12, slow=26, signal=9, symbol="UNKNOWN"):
    df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    log(f"[{symbol}] ✅ MACD calculé automatiquement.", level="INFO")
    return df

def calculate_rsi(df, period=14, symbol="UNKNOWN"):
    if len(df) < period:
        log(f"[{symbol}] [WARNING] Pas assez de données pour RSI ({len(df)} < {period}), signal ignoré.", level="DEBUG")
        return None

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)  # éviter division par zéro
    df['rsi'] = 100 - (100 / (1 + rs))

    # Au lieu de tester si *n'importe quel* NaN existe, on teste seulement la dernière valeur
    if pd.isna(df['rsi'].iloc[-1]):
        log(f"[{symbol}] ⚠️ Dernière valeur RSI est NaN — signal ignoré.", level="INFO")
        return None

    return df


def calculate_trix(df, period=9):
    ema1 = df['close'].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    df['trix'] = ema3.pct_change() * 100
    return df

def calculate_breakout_levels(df, window=20):
    df['high_breakout'] = df['high'].rolling(window=window).max()
    df['low_breakout'] = df['low'].rolling(window=window).min()
    return df

def compute_all(df, symbol=None):
    """
    Calcule tous les indicateurs nécessaires une seule fois.
    symbol est optionnel — s'il n'est pas fourni, on tente de le déduire du DataFrame.
    """
    df = df.copy()

    # Déduire le symbole si non fourni
    if symbol is None:
        if 'symbol' in df.columns and not df['symbol'].empty:
            symbol = str(df['symbol'].iloc[0])
        elif hasattr(df, 'attrs') and 'symbol' in df.attrs:
            symbol = df.attrs['symbol']
        else:
            symbol = "UNKNOWN"

    # MACD
    df = calculate_macd(df, symbol=symbol)

    # RSI
    df_rsi = calculate_rsi(df, symbol=symbol)
    if df_rsi is not None:
        df = df_rsi
    else:
        log(f"[{symbol}] [WARNING] RSI non calculé (données insuffisantes ou NaN permanents).", level="INFO")

    # TRIX & Breakout
    df = calculate_trix(df)
    df = calculate_breakout_levels(df)

    return df
