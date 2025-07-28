import asyncio
import asyncpg
import pandas as pd
import traceback
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal

async def fetch_ohlcv_from_db(pool, symbol):
    table_name = "ohlcv_" + "__".join(symbol.lower().split("_"))
    async with pool.acquire() as conn:
        try:
            query = f"""
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                WHERE interval_sec = 1
                ORDER BY timestamp ASC
            """
            rows = await conn.fetch(query)
            if not rows:
                log(f"[{symbol}] ❌ Pas de données OHLCV")
                return pd.DataFrame()
            df = pd.DataFrame([dict(row) for row in rows])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('Europe/Paris').dt.tz_convert('UTC')
            else:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
            df.set_index('timestamp', inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        except Exception as e:
            log(f"[{symbol}] ❌ Erreur fetch OHLCV backtest: {e}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, dsn: str, duration_hours: int = 24):
    pool = await asyncpg.create_pool(dsn=dsn)
    df = await fetch_ohlcv_from_db(pool, symbol)
    if df.empty:
        print(f"[{symbol}] ❌ Pas de données OHLCV")
        await pool.close()
        return

    # Limiter la durée du backtest aux dernières 'duration_hours' heures
    end_time = df.index.max()
    start_time = end_time - pd.Timedelta(hours=duration_hours)
    df = df.loc[start_time:end_time]

    print(f"[{symbol}] ✅ Données chargées pour backtest sur {duration_hours}h, {len(df)} lignes, de {start_time} à {end_time}")

    position = None  # None ou dict {'type': 'long'/'short', 'entry_price': float, 'entry_time': Timestamp}
    trades = []

    for timestamp, row in df.iterrows():
        # On analyse les données jusqu'à ce timestamp
        current_data = df.loc[:timestamp]

        # Calcul du signal
        signal = get_combined_signal(current_data)

        if position is None:
            if signal == 'BUY':
                position = {'type': 'long', 'entry_price': row['close'], 'entry_time': timestamp}
                print(f"{timestamp} - OUVERTURE LONG à {row['close']:.2f}")
            elif signal == 'SELL':
                position = {'type': 'short', 'entry_price': row['close'], 'entry_time': timestamp}
                print(f"{timestamp} - OUVERTURE SHORT à {row['close']:.2f}")
        else:
            # Position ouverte, on check si on doit fermer selon signal inverse
            if position['type'] == 'long' and signal == 'SELL':
                pnl = (row['close'] - position['entry_price']) / position['entry_price']
                print(f"{timestamp} - FERMETURE LONG à {row['close']:.2f}, PnL: {pnl*100:.2f}%")
                trades.append({'entry_time': position['entry_time'], 'exit_time': timestamp, 'pnl': pnl})
                position = None
            elif position['type'] == 'short' and signal == 'BUY':
                pnl = (position['entry_price'] - row['close']) / position['entry_price']
                print(f"{timestamp} - FERMETURE SHORT à {row['close']:.2f}, PnL: {pnl*100:.2f}%")
                trades.append({'entry_time': position['entry_time'], 'exit_time': timestamp, 'pnl': pnl})
                position = None

        # Ici tu peux ajouter la gestion de stop loss, take profit, trailing stop etc.

    # Si une position est toujours ouverte à la fin, la clôturer au dernier prix
    if position is not None:
        last_price = df.iloc[-1]['close']
        if position['type'] == 'long':
            pnl = (last_price - position['entry_price']) / position['entry_price']
        else:
            pnl = (position['entry_price'] - last_price) / position['entry_price']
        print(f"{df.index[-1]} - FERMETURE FORCEE à {last_price:.2f}, PnL: {pnl*100:.2f}%")
        trades.append({'entry_time': position['entry_time'], 'exit_time': df.index[-1], 'pnl': pnl})

    total_pnl = sum(t['pnl'] for t in trades)
    win_trades = [t for t in trades if t['pnl'] > 0]
    loss_trades = [t for t in trades if t['pnl'] <= 0]

    print(f"Backtest terminé sur {symbol}")
    print(f"Nombre de trades: {len(trades)}")
    print(f"Trades gagnants: {len(win_trades)}")
    print(f"Trades perdants: {len(loss_trades)}")
    print(f"PnL total: {total_pnl*100:.2f}%")
    if trades:
        print(f"PnL moyen: {total_pnl/len(trades)*100:.2f}%")

    await pool.close()


def run_backtest(symbol: str, duration_hours: int = 24):
    import os
    import asyncio
    dsn = os.environ.get("PG_DSN")
    asyncio.run(run_backtest_async(symbol, dsn, duration_hours))
