import pandas as pd
from datetime import timedelta
from utils.backtest_utils import analyze_results
from ScriptDatabase.pgsql_ohlcv import get_ohlcv_1s_sync
from signals.macd_rsi_breakout import get_combined_signal  # ou autre selon stratégie
import numpy as np

def simulate_trailing_stop(entry_price, df_slice, side, trailing_pct):
    highest_price = entry_price
    lowest_price = entry_price
    for current_time, row in df_slice.iterrows():
        price = row['close']

        if side == 'long':
            if price > highest_price:
                highest_price = price
            trailing_stop = highest_price * (1 - trailing_pct)
            if price <= trailing_stop:
                return price, current_time
        else:  # short
            if price < lowest_price:
                lowest_price = price
            trailing_stop = lowest_price * (1 + trailing_pct)
            if price >= trailing_stop:
                return price, current_time

    return df_slice.iloc[-1]['close'], df_slice.index[-1]

def run_backtest(symbol, start_date, end_date, signal_func=get_combined_signal, trailing_pct=0.01):
    df = get_ohlcv_1s_sync(symbol, start_date, end_date)

    if df.empty:
        print(f"[{symbol}] ❌ Aucune donnée pour la période demandée.")
        return []

    df_signals = signal_func(df.copy())
    results = []

    position = None

    for current_time in df_signals.index:
        row = df_signals.loc[current_time]
        signal = row.get('signal', None)

        if position:
            df_slice = df.loc[current_time:]
            exit_price, exit_time = simulate_trailing_stop(
                entry_price=position['entry_price'],
                df_slice=df_slice,
                side=position['side'],
                trailing_pct=trailing_pct
            )

            pnl = (exit_price - position['entry_price']) if position['side'] == 'long' else (position['entry_price'] - exit_price)
            pnl_pct = pnl / position['entry_price']

            results.append({
                'symbol': symbol,
                'side': position['side'],
                'entry_time': position['entry_time'],
                'entry_price': position['entry_price'],
                'exit_time': exit_time,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
            })

            position = None  # On clôt la position
            continue

        # Pas de position ouverte
        if signal == 'BUY':
            position = {
                'side': 'long',
                'entry_time': current_time,
                'entry_price': row['close']
            }
        elif signal == 'SELL':
            position = {
                'side': 'short',
                'entry_time': current_time,
                'entry_price': row['close']
            }

    return results

def backtest_main(symbols, start_date, end_date):
    all_results = []
    for symbol in symbols:
        print(f"🔁 Backtest en cours pour {symbol}")
        results = run_backtest(symbol, start_date, end_date)
        all_results.extend(results)

    df_results = pd.DataFrame(all_results)
    if df_results.empty:
        print("❌ Aucun trade simulé.")
        return

    analyze_results(df_results)
