# backtest/backtest_engine.py
import asyncio
import asyncpg
import re
import argparse
import pandas as pd
import os
import traceback
from utils.logger import log
from utils.position_utils import PositionTracker
from utils.i18n import t
from importlib import import_module
from datetime import datetime, timedelta, timezone

def get_signal_function(strategy_name):
    """Charge dynamiquement la stratégie demandée"""
    if strategy_name == "Trix":
        module = import_module("signals.trix_only_signal")
    elif strategy_name == "Combo":
        module = import_module("signals.macd_rsi_bo_trix")
    else:
        module = import_module("signals.macd_rsi_breakout")
    return module.get_combined_signal

def parse_backtest(value):
    """Parse les arguments de backtest (durée ou plage de dates)"""
    if ":" in value and re.match(r"^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$", value):
        start_str, end_str = value.split(":")
        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_str, "%Y-%m-%d")
        if start_dt >= end_dt:
            raise argparse.ArgumentTypeError("La date de début doit être avant la date de fin.")
        return (start_dt, end_dt)

    match = re.match(r"^(\d+)([smhdw]?)$", value.lower())
    if not match:
        raise argparse.ArgumentTypeError(
            "Format invalide. Utilise par ex: 10m, 2h, 3d, 1w, juste un nombre (minutes), "
            "ou plage de dates YYYY-MM-DD:YYYY-MM-DD"
        )
    amount, unit = match.groups()
    amount = int(amount)
    multipliers_in_hours = {
        "": 1/60,  # minutes par défaut
        "s": 1/3600,
        "m": 1/60,
        "h": 1,
        "d": 24,
        "w": 168
    }
    return amount * multipliers_in_hours[unit]

async def fetch_ohlcv_from_db(pool, symbol):
    """Récupère les données OHLCV depuis la base PostgreSQL"""
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
                log(f"[{symbol}] {t('backtest', 'no_ohlcv_data')}")
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
            log(f"[{symbol}] {t('backtest', 'error_fetch_ohlcv', str(e))}")
            traceback.print_exc()
            return pd.DataFrame()

async def run_backtest_async(symbol: str, interval, dsn: str, strategy_name: str):
    try:
        pool = await asyncpg.create_pool(dsn=dsn)
        df = await fetch_ohlcv_from_db(pool, symbol)
        await pool.close()

        if df.empty:
            log(f"[{symbol}] {t('backtest', 'no_data')}")
            return
        
        # Filtrage des données selon interval
        if isinstance(interval, (int, float)):
            # interval en heures, on prend les dernières interval heures
            end_time = df.index[-1]
            start_time = end_time - timedelta(hours=interval)
            df = df.loc[start_time:end_time]
            log(f"[{symbol}] Filtrage sur les dernières {interval} heures")
        elif isinstance(interval, tuple) and len(interval) == 2:
            start_time, end_time = interval
            # Assurer que start_time et end_time ont le bon timezone (UTC)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            df = df.loc[start_time:end_time]
            log(f"[{symbol}] Filtrage entre {start_time} et {end_time}")

        if df.empty:
            log(f"[{symbol}] {t('backtest', 'no_data_after_filter')}")
            return

        log(f"[{symbol}] {t('backtest', 'start', len(df))}")

        tracker = PositionTracker(symbol)
        stats = {"total": 0, "win": 0, "loss": 0, "pnl": []}

        get_combined_signal = get_signal_function(strategy_name)

        for current_time in df.index:
            current_df = df.loc[:current_time]
            if len(current_df) < 100:
                continue

            result = get_combined_signal(current_df)
            if isinstance(result, tuple):
                signal, indicators = result
            else:
                signal = result
                indicators = {}
            
            debug_msg = f"[DEBUG] {symbol} | {current_time} | Signal={signal} | Prix={current_df.iloc[-1]['close']}"
            if indicators:
                debug_msg += " | " + " | ".join(f"{k}={v:.2f}" for k, v in indicators.items())
            log(debug_msg, level="DEBUG")

            current_price = current_df.iloc[-1]["close"]

            # Ouvre position si signal et aucune position
            if signal in ("BUY", "SELL") and not tracker.is_open():
                tracker.open(signal, current_price, current_time)

            # Met à jour trailing stop si position ouverte
            if tracker.is_open():
                tracker.update_trailing_stop(current_price, current_time)

                # Ferme si stop touché
                if tracker.should_close(current_price):
                    pnl = tracker.close(current_price, current_time)
                    stats["total"] += 1
                    stats["pnl"].append(pnl)
                    if pnl >= 0:
                        stats["win"] += 1
                    else:
                        stats["loss"] += 1

        log(f"[{symbol}] {t('backtest', 'end')}")
        
        if stats["total"] > 0:
            pnl_total = sum(stats["pnl"])
            pnl_moyen = pnl_total / stats["total"]
            pnl_median = pd.Series(stats["pnl"]).median()
            win_rate = stats["win"] / stats["total"] * 100
            
            log(f"[{symbol}] {t('backtest', 'stats_positions', stats['total'], stats['win'], stats['loss'])}")
            log(f"[{symbol}] {t('backtest', 'stats_pnl', pnl_total, pnl_moyen, pnl_median, win_rate)}")
        else:
            log(f"[{symbol}] {t('backtest', 'no_positions')}")

    except Exception as e:
        log(f"[{symbol}] {t('backtest', 'exception', str(e))}")
        traceback.print_exc()

def run_backtest(symbol: str, interval: str, strategy_name: str):
    dsn = os.environ.get("PG_DSN")
    asyncio.run(run_backtest_async(symbol, interval, dsn, strategy_name))

def get_supported_languages():
    try:
        from utils.i18n import get_available_locales
        return get_available_locales()
    except ImportError:
        return ['fr', 'en']