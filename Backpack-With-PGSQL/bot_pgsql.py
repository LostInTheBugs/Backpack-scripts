import time
import argparse
import os
from datetime import datetime, timezone, timedelta
import pandas as pd
import pandas_ta as ta
import numpy as np
import asyncpg
import asyncio

from read.breakout_signal import breakout_signal
from read.open_position_utils import has_open_position, get_position_pnl
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

POSITION_AMOUNT_USDC = 20
RESELECT_INTERVAL_SEC = 300
TRAILING_STOP_PCT = 0.005

PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    raise RuntimeError("La variable d'environnement PG_DSN n'est pas définie")

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def prepare_ohlcv_df(ohlcv):
    df = pd.DataFrame(ohlcv)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def calculate_macd_rsi(df):
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['rsi'] = ta.rsi(df['close'], length=14)
    return df

def combined_signal(df):
    df = df.copy()
    df['ema50'] = ta.ema(df['close'], length=50)
    macd_df = ta.macd(df['close'])
    df['macd'] = macd_df.iloc[:, 0]
    df['macd_signal'] = macd_df.iloc[:, 1]
    df['rsi'] = ta.rsi(df['close'], length=14)

    if df[['ema50', 'macd', 'macd_signal', 'rsi']].iloc[-1].isnull().any():
        return None

    signal = None
    if df['high'].iloc[-1] > df['high'].iloc[-2] and df['close'].iloc[-1] > df['high'].iloc[-2]:
        if df['close'].iloc[-1] < df['ema50'].iloc[-1]:
            print(f"❌ Signal BUY rejeté : close ({df['close'].iloc[-1]:.4f}) < ema50 ({df['ema50'].iloc[-1]:.4f})")
        elif df['macd'].iloc[-1] <= df['macd_signal'].iloc[-1]:
            print("❌ Signal BUY rejeté : MACD haussier absent")
        elif df['rsi'].iloc[-1] > 70:
            print("❌ Signal BUY rejeté : RSI trop élevé")
        else:
            signal = 'BUY'

    elif df['low'].iloc[-1] < df['low'].iloc[-2] and df['close'].iloc[-1] < df['low'].iloc[-2]:
        if df['close'].iloc[-1] >= df['ema50'].iloc[-1]:
            print(f"❌ Signal SELL rejeté : close ({df['close'].iloc[-1]:.4f}) >= ema50 ({df['ema50'].iloc[-1]:.4f})")
        elif df['macd'].iloc[-1] >= df['macd_signal'].iloc[-1]:
            print("❌ Signal SELL rejeté : MACD baissier absent")
        elif df['rsi'].iloc[-1] < 30:
            print("❌ Signal SELL rejeté : RSI trop bas")
        else:
            signal = 'SELL'

    return signal

def read_symbols_from_file(filepath="symbol.lst"):
    try:
        with open(filepath, "r") as f:
            symbols = [line.strip() for line in f if line.strip()]
        if not symbols:
            log(f"⚠️ Le fichier {filepath} est vide.")
        return symbols
    except FileNotFoundError:
        log(f"❌ Fichier {filepath} non trouvé.")
        return []

async def fetch_ohlcv_from_pg(pool, symbol, minutes):
    table_name = "ohlcv_" + symbol.lower().replace("_", "__")
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    query = f"""
        SELECT timestamp, open, high, low, close, volume
        FROM {table_name}
        WHERE timestamp >= $1
        ORDER BY timestamp ASC
        LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, cutoff, minutes)
    data = [{
        "timestamp": r["timestamp"],
        "open": r["open"],
        "high": r["high"],
        "low": r["low"],
        "close": r["close"],
        "volume": r["volume"]
    } for r in rows]
    return data

def duration_to_minutes(duration: str) -> int:
    duration = duration.lower()
    if duration.endswith("m"):
        return int(duration[:-1])
    elif duration.endswith("h"):
        return int(duration[:-1]) * 60
    elif duration.endswith("d"):
        val = int(duration[:-1])
        if val > 90:
            val = 90
        return val * 60 * 24
    elif duration.endswith("w"):
        val = int(duration[:-1])
        return val * 60 * 24 * 7
    else:
        raise ValueError("Durée non reconnue. Utilisez un format comme 15m, 1h, 1d, 1w.")

def handle_live_symbol(symbol: str, real_run: bool):
    # Ton code actuel de trading live ici
    pass

async def backtest_symbol(pool, symbol: str, duration: str):
    minutes = duration_to_minutes(duration)
    ohlcv = await fetch_ohlcv_from_pg(pool, symbol, minutes)
    if not ohlcv or len(ohlcv) < 60:
        log(f"[{symbol}] ⚠️ Pas assez de données pour backtest")
        return
    df = prepare_ohlcv_df(ohlcv)
    df['ema50'] = ta.ema(df['close'], length=50)
    macd_df = ta.macd(df['close'])
    df['macd'] = macd_df.iloc[:, 0]
    df['macd_signal'] = macd_df.iloc[:, 1]
    df['rsi'] = ta.rsi(df['close'], length=14)

    trades = []
    position = None
    entry_price = None
    max_price = None
    min_price = None

    for i in range(50, len(df)):
        row = df.iloc[i]
        if pd.isna(row['ema50']) or pd.isna(row['macd']) or pd.isna(row['macd_signal']) or pd.isna(row['rsi']):
            continue
        df_slice = df.iloc[:i+1]
        signal = combined_signal(df_slice)
        close_price = row['close']

        if position is None:
            if signal == "BUY":
                position = "long"
                entry_price = close_price
                max_price = close_price
                min_price = close_price
            elif signal == "SELL":
                position = "short"
                entry_price = close_price
                max_price = close_price
                min_price = close_price
        else:
            if position == "long":
                if close_price > max_price:
                    max_price = close_price
                if close_price < max_price * (1 - TRAILING_STOP_PCT):
                    pnl = (close_price - entry_price) / entry_price
                    trades.append({"type": position, "entry": entry_price, "exit": close_price, "pnl": pnl})
                    position = None
                    continue
                if signal == "SELL":
                    pnl = (close_price - entry_price) / entry_price
                    trades.append({"type": position, "entry": entry_price, "exit": close_price, "pnl": pnl})
                    position = None
                    continue
            elif position == "short":
                if close_price < min_price:
                    min_price = close_price
                if close_price > min_price * (1 + TRAILING_STOP_PCT):
                    pnl = (entry_price - close_price) / entry_price
                    trades.append({"type": position, "entry": entry_price, "exit": close_price, "pnl": pnl})
                    position = None
                    continue
                if signal == "BUY":
                    pnl = (entry_price - close_price) / entry_price
                    trades.append({"type": position, "entry": entry_price, "exit": close_price, "pnl": pnl})
                    position = None
                    continue

    if position is not None:
        exit_price = df['close'].iloc[-1]
        if position == "long":
            pnl = (exit_price - entry_price) / entry_price
        else:
            pnl = (entry_price - exit_price) / entry_price
        trades.append({"type": position, "entry": entry_price, "exit": exit_price, "pnl": pnl})

    total_pnl = sum(t['pnl'] for t in trades)
    log(f"[{symbol}] Backtest sur {duration} : {len(trades)} trades, PnL total: {total_pnl*100:.2f}%")
    for i, t in enumerate(trades):
        log(f"  Trade {i+1}: {t['type']} entry={t['entry']:.4f} exit={t['exit']:.4f} pnl={t['pnl']*100:.2f}%")

def select_symbols_by_volatility():
    # Ta fonction existante, inchangée ou à ajouter ici
    return []

def main_loop(symbols: list, real_run: bool, auto_select=False):
    last_selection_time = 0

    while True:
        if auto_select and (time.time() - last_selection_time > RESELECT_INTERVAL_SEC):
            symbols = select_symbols_by_volatility()
            last_selection_time = time.time()
            log(f"🔄 Nouvelle sélection automatique de symbols : {', '.join(symbols)}")

        for symbol in symbols:
            handle_live_symbol(symbol, real_run)

        time.sleep(1)

if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs='?', default="", help="Liste des symboles séparés par des virgules (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symbols par volatilité")
    parser.add_argument("--backtest", type=str, help="Backtest sur une période: 1m, 15m, 1h, 1d, 1w")
    args = parser.parse_args()

    def get_symbols():
        if args.auto_select:
            return select_symbols_by_volatility()
        elif args.symbols:
            return [s.strip() for s in args.symbols.split(",") if s.strip()]
        else:
            return read_symbols_from_file()

    symbols = get_symbols()

    if args.backtest:
        async def run_backtests():
            pool = await asyncpg.create_pool(dsn=PG_DSN)
            for sym in symbols:
                await backtest_symbol(pool, sym, args.backtest)
            await pool.close()

        asyncio.run(run_backtests())
    else:
        main_loop(symbols, real_run=args.real_run, auto_select=args.auto_select)
