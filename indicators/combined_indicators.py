import os
import pandas as pd
import psycopg2
from utils.logger import log

# Lecture de la connexion PostgreSQL via la variable d'environnement PG_DSN
PG_DSN = os.environ.get("PG_DSN")

def load_ohlcv_from_db(symbol, limit=500):
    """
    Charge les données OHLCV depuis PostgreSQL pour un symbole donné.
    limit = nombre de lignes récentes à récupérer (par défaut 500)
    Retourne un DataFrame pandas avec un index datetime.
    """
    if not PG_DSN:
        log("[DB] PG_DSN non configuré, impossible de charger les données en base.", level="ERROR")
        return None
    
    query = f"""
    SELECT
        time,
        open,
        high,
        low,
        close,
        volume
    FROM ohlcv
    WHERE symbol = %s
    ORDER BY time DESC
    LIMIT %s
    """

    try:
        with psycopg2.connect(PG_DSN) as conn:
            df = pd.read_sql(query, conn, params=(symbol, limit))
        if df.empty:
            log(f"[DB] Aucune donnée trouvée pour {symbol}", level="WARNING")
            return None
        # Mise en index datetime, tri chronologique ascendant
        df['time'] = pd.to_datetime(df['time'])
        df = df.set_index('time').sort_index()
        return df
    except Exception as e:
        log(f"[DB] Erreur lors du chargement des données {symbol} : {e}", level="ERROR")
        return None

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
    rs = avg_gain / (avg_loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Remplacer les NaN initiaux par la première valeur non-NaN
    first_valid_idx = df['rsi'].first_valid_index()
    if first_valid_idx is not None:
        df['rsi'].fillna(method='bfill', inplace=True)
        log(f"[{symbol}] RSI premiers NaN remplacés par backward fill à partir de l'index {first_valid_idx}", level="DEBUG")

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
    df = df.copy()

    # Déduire symbole si besoin
    if symbol is None:
        if 'symbol' in df.columns and not df['symbol'].empty:
            symbol = str(df['symbol'].iloc[0])
        elif hasattr(df, 'attrs') and 'symbol' in df.attrs:
            symbol = df.attrs['symbol']
        else:
            symbol = "UNKNOWN"

    df = calculate_macd(df, symbol=symbol)

    df_rsi = calculate_rsi(df, symbol=symbol)
    if df_rsi is not None:
        df = df_rsi  # <-- ici on met à jour df avec le RSI calculé
        log(f"[{symbol}] ✅ RSI calculé avec succès.", level="INFO")
    else:
        log(f"[{symbol}] [WARNING] RSI non calculé (données insuffisantes ou NaN permanents).", level="INFO")

    df = calculate_trix(df)
    df = calculate_breakout_levels(df)

    return df
