import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
import inspect

from utils.position_utils import position_already_open, get_real_pnl, get_open_positions
from utils.logger import log
from utils.public import check_table_and_fresh_data
from execute.async_wrappers import open_position_async, close_position_percent_async
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from signals.strategy_selector import get_strategy_for_market
from config.settings import get_config
from indicators.rsi_calculator import get_cached_rsi

# Load configuration
config = get_config()
trading_config = config.trading

INTERVAL = "1s"
POSITION_AMOUNT_USDC = trading_config.position_amount_usdc
LEVERAGE = trading_config.leverage
TRAILING_STOP_TRIGGER = trading_config.trailing_stop_trigger
MIN_PNL_FOR_TRAILING = trading_config.min_pnl_for_trailing

MAX_PNL_TRACKER = {}  # Tracker for max PnL per symbol

public_key = config.bpx_bot_public_key or os.environ.get("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.environ.get("bpx_bot_secret_key")


async def scan_all_symbols(pool, symbols):
    log("[INFO] 🔍 Lancement du scan indicateurs…", level="INFO")
    ok_symbols, ko_symbols = [], []

    for symbol in symbols:
        try:
            end_ts = datetime.now(timezone.utc)
            start_ts = end_ts - timedelta(seconds=60)
            df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
            if df is None or df.empty:
                ko_symbols.append((symbol, "No data"))
                continue

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
            df.set_index('timestamp', inplace=True)
            df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)

            df_checked = await ensure_indicators(df, symbol)
            if df_checked is None:
                ko_symbols.append((symbol, "Missing/NaN indicators"))
            else:
                ok_symbols.append(symbol)

        except Exception as e:
            ko_symbols.append((symbol, f"Error: {e}"))

    log(f"[INFO] ✅ OK: {ok_symbols}", level="INFO")
    log(f"[INFO] ❌ KO: {ko_symbols}", level="INFO")
    log(f"[INFO] 📊 Résumé: {len(ok_symbols)} OK / {len(ko_symbols)} KO sur {len(symbols)} paires.", level="INFO")


def import_strategy_signal(strategy):
    if strategy == "Trix":
        from signals.trix_only_signal import get_combined_signal
    elif strategy == "Combo":
        from signals.macd_rsi_bo_trix import get_combined_signal
    elif strategy == "Range":
        from signals.range_signal import get_combined_signal
    elif strategy == "RangeSoft":
        from signals.range_soft_signal import get_combined_signal
    elif strategy == "AutoSoft":
        from signals.strategy_selector import strategy_autosoft as get_combined_signal
    elif strategy == "DynamicThreeTwo":
        from signals.dynamic_three_two_selector import get_combined_signal
    elif strategy == "ThreeOutOfFour":
        from signals.three_out_of_four_conditions import get_combined_signal
    elif strategy == "TwoOutOfFourScalp":
        from signals.two_out_of_four_scalp import get_combined_signal
    else:
        from signals.macd_rsi_breakout import get_combined_signal
    return get_combined_signal


async def ensure_indicators(df, symbol):
    required_cols = ["EMA20", "EMA50", "EMA200", "RSI", "MACD"]
    for period, col in [(20,"EMA20"),(50,"EMA50"),(200,"EMA200")]:
        if col not in df.columns:
            df[col] = df['close'].ewm(span=period, adjust=False).mean()

    try:
        rsi_value = await get_cached_rsi(symbol, interval="5m")
        df['RSI'] = rsi_value
        log(f"[DEBUG] [{symbol}] ✅ RSI récupéré via API: {rsi_value:.2f}", level="DEBUG")
    except Exception as e:
        log(f"[WARNING] [{symbol}] ⚠️ Erreur RSI API, tentative calcul local: {e}", level="WARNING")
        try:
            from indicators.rsi_calculator import calculate_rsi
            rsi_value = calculate_rsi(df['close'], period=14)
            df['RSI'] = rsi_value
            log(f"[INFO] [{symbol}] 🔄 RSI calculé localement: {rsi_value.iloc[-1]:.2f}", level="INFO")
        except Exception as e2:
            df['RSI'] = 50
            log(f"[ERROR] [{symbol}] ⚠️ Impossible de calculer RSI localement, utilisation valeur neutre: {e2}", level="ERROR")

    if 'MACD' not in df.columns or 'MACD_signal' not in df.columns:
        short_window, long_window, signal_window = 12,26,9
        ema_short = df['close'].ewm(span=short_window, adjust=False).mean()
        ema_long = df['close'].ewm(span=long_window, adjust=False).mean()
        df['MACD'] = ema_short - ema_long
        df['MACD_signal'] = df['MACD'].ewm(span=signal_window, adjust=False).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
        log(f"[INFO] [{symbol}] ✅ MACD calculé automatiquement.", level="INFO")

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        log(f"[WARNING] [{symbol}] ⚠️ Indicateurs manquants: {missing} — signal ignoré.", level="WARNING")
        return None

    for col in required_cols:
        if col != 'RSI' and df[col].isna().any():
            log(f"[WARNING] [{symbol}] ⚠️ NaN détecté dans {col} — signal ignoré.", level="WARNING")
            return None

    return df


async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool, args=None):
    try:
        log(f"[DEBUG] [{symbol}] 📈 Loading OHLCV data for {INTERVAL}", level="DEBUG")
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
            log(f"[ERROR] [{symbol}] ❌ Ignored: no recent data in local database", level="ERROR")
            return

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=600)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
        if df is None or df.empty:
            log(f"[ERROR] [{symbol}] ❌ No 1s data retrieved from local database", level="ERROR")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)

        if args.strategie == "Auto":
            market_condition, selected_strategy = get_strategy_for_market(df)
            log(f"[INFO] [{symbol}] 📊 Market detected: {market_condition.upper()} — Strategy selected: {selected_strategy}", level="INFO")
        else:
            selected_strategy = args.strategie
            log(f"[INFO] [{symbol}] 📊 Strategy manually selected: {selected_strategy}", level="INFO")

        get_combined_signal = import_strategy_signal(selected_strategy)

        df = await ensure_indicators(df, symbol)
        if df is None:
            return

        if inspect.iscoroutinefunction(get_combined_signal):
            signal, details = await get_combined_signal(df, symbol)
        else:
            signal, details = get_combined_signal(df, symbol)

        log(f"[INFO] [{symbol}] 🎯 Signal detected: {signal} | Details: {details}", level="INFO")

        if await position_already_open(symbol):
            await handle_existing_position(symbol, real_run, dry_run)
            return

        if signal in ["BUY","SELL"]:
            await handle_new_position(symbol, signal, real_run, dry_run)
            log(f"[DEBUG] {symbol} 🚨 Try open position: {signal}", level="DEBUG")
        else:
            log(f"[DEBUG] {symbol} ❌ No actionable signal detected: {signal}", level="DEBUG")

    except Exception as e:
        log(f"[{symbol}] 💥 Error: {e}")
        traceback.print_exc()


async def handle_existing_position(symbol: str, real_run: bool, dry_run: bool):
    pnl_usdc, _ = await get_real_pnl(symbol)
    pnl_percent = (pnl_usdc / (POSITION_AMOUNT_USDC / LEVERAGE)) * 100

    max_pnl = MAX_PNL_TRACKER.get(symbol, pnl_percent)
    if pnl_percent > max_pnl:
        MAX_PNL_TRACKER[symbol] = pnl_percent
        max_pnl = pnl_percent

    if max_pnl >= MIN_PNL_FOR_TRAILING and (max_pnl - pnl_percent) >= TRAILING_STOP_TRIGGER:
        log(f"[INFO] [{symbol}] ⛔ Trailing stop triggered: PnL {pnl_percent:.2f}% < Max {max_pnl:.2f}% - {TRAILING_STOP_TRIGGER}%", level="INFO")
        if real_run:
            try:
                await close_position_percent_async(symbol, percent=100)
                log(f"[INFO] [{symbol}] ✅ Position closed successfully via trailing stop", level="INFO")
            except Exception as e:
                log(f"[ERROR] [{symbol}] ❌ Error closing position: {e}", level="ERROR")
        else:
            log(f"[INFO] [{symbol}] 🧪 DRY-RUN: Simulated close via trailing stop", level="INFO")
        MAX_PNL_TRACKER.pop(symbol, None)
    else:
        log(f"[INFO] [{symbol}] 🔄 Current PnL: {pnl_percent:.2f}% | Max: {max_pnl:.2f}% | Min for trailing: {MIN_PNL_FOR_TRAILING:.1f}%", level="INFO")
        MAX_PNL_TRACKER[symbol] = max_pnl

    log(f"[WARNING] [{symbol}] ⚠️ Position already open — Monitoring (trailing stop active)", level="WARNING")


async def handle_new_position(symbol: str, signal: str, real_run: bool, dry_run: bool):
    direction = "long" if signal=="BUY" else "short"
    
    if real_run and not await check_position_limit():
        log(f"[WARNING] [{symbol}] ⚠️ Maximum positions limit ({trading_config.max_positions}) reached - skipping", level="WARNING")
        return

    if dry_run:
        log(f"[INFO] [{symbol}] 🧪 DRY-RUN: Simulated {direction.upper()} position opening", level="INFO")
    elif real_run:
        log(f"[INFO] [{symbol}] ✅ REAL position opening: {direction.upper()}", level="INFO")
        try:
            await open_position_async(symbol, POSITION_AMOUNT_USDC, direction)
            MAX_PNL_TRACKER[symbol] = 0.0
            log(f"[INFO] [{symbol}] ✅ Position opened successfully", level="INFO")
        except Exception as e:
            log(f"[ERROR] [{symbol}] ❌ Error opening position: {e}", level="ERROR")
    else:
        log(f"[ERROR] [{symbol}] ❌ Neither --real-run nor --dry-run specified: no action", level="ERROR")


async def check_position_limit() -> bool:
    try:
        positions = await get_open_positions()  # async version
        current_positions = len([p for p in positions.values() if p])
        return current_positions < trading_config.max_positions
    except Exception as e:
        log(f"[WARNING] ⚠️ Error checking position limit: {e}", level="WARNING")
        return True


async def get_position_stats() -> dict:
    try:
        positions = await get_open_positions()
        return {
            'total_positions': len([p for p in positions.values() if p]),
            'max_positions': trading_config.max_positions,
            'position_amount': POSITION_AMOUNT_USDC,
            'leverage': LEVERAGE,
            'trailing_stop_trigger': TRAILING_STOP_TRIGGER,
            'min_pnl_for_trailing': MIN_PNL_FOR_TRAILING
        }
    except Exception as e:
        log(f"[ERROR] ⚠️ Error getting position stats: {e}", level="ERROR")
        return {}
