#live/live_engine.py
import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
import inspect
import asyncio

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

def get_handle_live_symbol():
    """
    SOLUTION: Lazy import to break circular dependency
    Only import handle_live_symbol when actually needed
    """
    from live.live_engine import handle_live_symbol
    return handle_live_symbol

async def scan_all_symbols(pool, symbols):
    log("🔍 Lancement du scan indicateurs…", level="INFO")
    tasks = [scan_symbol(pool, symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok_symbols, ko_symbols = [], []
    for res in results:
        if isinstance(res, tuple) and len(res) == 2:
            symbol, status = res
            if status == "OK":
                ok_symbols.append(symbol)
            else:
                ko_symbols.append((symbol, status))
        else:
            log(f"⚠️ Unexpected result in scan_all_symbols: {res}", level="WARNING")

    log(f"✅ OK: {ok_symbols}", level="DEBUG")
    log(f"❌ KO: {ko_symbols}", level="DEBUG")
    log(f"📊 Résumé: {len(ok_symbols)} OK / {len(ko_symbols)} KO sur {len(symbols)} paires.", level="DEBUG")


async def scan_symbol(pool, symbol):
    try:
        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=60)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts, pool=pool)
        if df is None or df.empty:
            return symbol, "No data"

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)

        df_checked = await ensure_indicators(df, symbol)
        if df_checked is None:
            return symbol, "Missing/NaN indicators"
        return symbol, "OK"
    except Exception as e:
        return symbol, f"Error: {e}"


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
    """
    ✅ CORRECTION: Cette fonction est maintenant async car elle appelle get_cached_rsi
    """
    required_cols = ["EMA20", "EMA50", "EMA200", "RSI", "MACD"]
    for period, col in [(20,"EMA20"),(50,"EMA50"),(200,"EMA200")]:
        if col not in df.columns:
            df[col] = df['close'].ewm(span=period, adjust=False).mean()

    try:
        rsi_value = await get_cached_rsi(symbol, interval="5m")
        df['RSI'] = rsi_value
        log(f"[{symbol}] ✅ RSI récupéré via API: {rsi_value:.2f}", level="DEBUG")
    except Exception as e:
        log(f"[{symbol}] ⚠️ Erreur RSI API, tentative calcul local: {e}", level="WARNING")
        try:
            from indicators.rsi_calculator import calculate_rsi
            rsi_value = calculate_rsi(df['close'], period=14)
            df['RSI'] = rsi_value
            log(f"[{symbol}] 🔄 RSI calculé localement: {rsi_value.iloc[-1]:.2f}", level="DEBUG")
        except Exception as e2:
            df['RSI'] = 50
            log(f"[{symbol}] ⚠️ Impossible de calculer RSI localement, valeur neutre: {e2}", level="ERROR")

    if 'MACD' not in df.columns or 'MACD_signal' not in df.columns:
        short_window, long_window, signal_window = 12,26,9
        ema_short = df['close'].ewm(span=short_window, adjust=False).mean()
        ema_long = df['close'].ewm(span=long_window, adjust=False).mean()
        df['MACD'] = ema_short - ema_long
        df['MACD_signal'] = df['MACD'].ewm(span=signal_window, adjust=False).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
        log(f"[{symbol}] ✅ MACD calculé automatiquement.", level="DEBUG")

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        log(f"[{symbol}] ⚠️ Indicateurs manquants: {missing} — signal ignoré.", level="WARNING")
        return None

    for col in required_cols:
        if col != 'RSI' and df[col].isna().any():
            log(f"[{symbol}] ⚠️ NaN détecté dans {col} — signal ignoré.", level="WARNING")
            return None

    return df


async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool, args=None):
    try:
        log(f"[{symbol}] 📈 Loading OHLCV data for {INTERVAL}", level="DEBUG")
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
            log(f"[{symbol}] ❌ Ignored: no recent data in local database", level="ERROR")
            return

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=600)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts, pool=pool)
        if df is None or df.empty:
            log(f"[{symbol}] ❌ No 1s data retrieved from local database", level="ERROR")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)

        if args.strategie == "Auto":
            market_condition, selected_strategy = get_strategy_for_market(df)
            log(f"[{symbol}] 📊 Market detected: {market_condition.upper()} — Strategy selected: {selected_strategy}", level="DEBUG")
        else:
            selected_strategy = args.strategie
            log(f"[{symbol}] 📊 Strategy manually selected: {selected_strategy}", level="DEBUG")

        get_combined_signal = import_strategy_signal(selected_strategy)
        
        # ✅ CORRECTION: ensure_indicators est maintenant async, donc on peut l'awaiter
        df_result = await ensure_indicators(df, symbol)
        
        # 🔍 DEBUG: Vérification détaillée du type de retour
        log(f"[{symbol}] ensure_indicators returned type: {type(df_result)}", level="DEBUG")
        log(f"[{symbol}] Is coroutine? {asyncio.iscoroutine(df_result)}", level="DEBUG")
        
        # Si c'est une coroutine, on l'await
        if asyncio.iscoroutine(df_result):
            log(f"[{symbol}] Awaiting coroutine from ensure_indicators...", level="DEBUG")
            df = await df_result
        else:
            df = df_result
            
        if df is None:
            log(f"[{symbol}] ❌ Indicators calculation failed", level="ERROR")
            return

        # ✅ CORRECTION: Vérification robuste du type de df avant de l'utiliser
        if not isinstance(df, pd.DataFrame):
            log(f"[{symbol}] ❌ Expected DataFrame but got {type(df)}", level="ERROR")
            return
            
        if df.empty:
            log(f"[{symbol}] ⚠️ DataFrame is empty after indicators calculation", level="WARNING")
            return
            
        # 🔍 DEBUG: Validation finale du DataFrame
        log(f"[{symbol}] DataFrame validated - shape: {df.shape}, columns: {list(df.columns)}", level="DEBUG")

        # ✅ CORRECTION: Vérification si get_combined_signal est async et gestion appropriée
        try:
            # 🔍 DEBUG: Logs détaillés avant l'appel
            log(f"[{symbol}] About to call strategy: {selected_strategy}", level="DEBUG")
            log(f"[{symbol}] Function type: {type(get_combined_signal)}", level="DEBUG")
            log(f"[{symbol}] Is coroutine function? {inspect.iscoroutinefunction(get_combined_signal)}", level="DEBUG")
            log(f"[{symbol}] DataFrame type before call: {type(df)}", level="DEBUG")
            log(f"[{symbol}] DataFrame shape: {df.shape}", level="DEBUG")
            
            if inspect.iscoroutinefunction(get_combined_signal):
                log(f"[{symbol}] 🔄 Calling async strategy function", level="DEBUG")
                result = await get_combined_signal(df, symbol)
            else:
                log(f"[{symbol}] 🔄 Calling sync strategy function", level="DEBUG")
                result = get_combined_signal(df, symbol)
                
            log(f"[{symbol}] Strategy returned: {type(result)} - {result}", level="DEBUG")
            
        except Exception as e:
            log(f"[{symbol}] ❌ Error calling strategy function: {e}", level="ERROR")
            log(f"[{symbol}] DataFrame info at time of error:", level="ERROR")
            log(f"[{symbol}]   - Type: {type(df)}", level="ERROR")
            log(f"[{symbol}]   - Is coroutine? {asyncio.iscoroutine(df)}", level="ERROR")
            if hasattr(df, 'shape'):
                log(f"[{symbol}]   - Shape: {df.shape}", level="ERROR")
            if hasattr(df, 'columns'):
                log(f"[{symbol}]   - Columns: {list(df.columns)}", level="ERROR")
            traceback.print_exc()
            return

        # Vérifie si result est un tuple/list à deux éléments
        if isinstance(result, (tuple, list)) and len(result) == 2:
            signal, details = result
        else:
            signal = result
            details = {}  # valeur vide si la stratégie ne renvoie pas de détails

        log(f"[{symbol}] 🎯 Signal detected: {signal} | Details: {details}", level="DEBUG")

        if await position_already_open(symbol):
            await handle_existing_position(symbol, real_run, dry_run)
            return

        if signal in ["BUY","SELL"]:
            await handle_new_position(symbol, signal, real_run, dry_run)
            log(f"{symbol} 🚨 Try open position: {signal}", level="DEBUG")
        else:
            log(f"{symbol} ❌ No actionable signal detected: {signal}", level="DEBUG")

    except Exception as e:
        log(f"[{symbol}] 💥 Error: {e}", level="ERROR")
        traceback.print_exc()


async def handle_existing_position(symbol: str, real_run: bool, dry_run: bool):
    pnl_usdc, _ = await get_real_pnl(symbol)
    pnl_percent = (pnl_usdc / (POSITION_AMOUNT_USDC / LEVERAGE)) * 100
    max_pnl = MAX_PNL_TRACKER.get(symbol, pnl_percent)
    if pnl_percent > max_pnl:
        MAX_PNL_TRACKER[symbol] = pnl_percent
        max_pnl = pnl_percent

    if max_pnl >= MIN_PNL_FOR_TRAILING and (max_pnl - pnl_percent) >= TRAILING_STOP_TRIGGER:
        log(f"[{symbol}] ⛔ Trailing stop triggered: PnL {pnl_percent:.2f}% < Max {max_pnl:.2f}% - {TRAILING_STOP_TRIGGER}%", level="DEBUG")
        if real_run:
            try:
                await close_position_percent_async(symbol, percent=100)
                log(f"[{symbol}] ✅ Position closed successfully via trailing stop", level="DEBUG")
            except Exception as e:
                log(f"[{symbol}] ❌ Error closing position: {e}", level="ERROR")
        else:
            log(f"[{symbol}] 🧪 DRY-RUN: Simulated close via trailing stop", level="DEBUG")
        MAX_PNL_TRACKER.pop(symbol, None)
    else:
        log(f"[{symbol}] 🔄 Current PnL: {pnl_percent:.2f}% | Max: {max_pnl:.2f}% | Min for trailing: {MIN_PNL_FOR_TRAILING:.1f}%", level="DEBUG")
        MAX_PNL_TRACKER[symbol] = max_pnl

    log(f"[{symbol}] ⚠️ Position already open — Monitoring (trailing stop active)", level="DEBUG")


async def handle_new_position(symbol: str, signal: str, real_run: bool, dry_run: bool):
    direction = "long" if signal=="BUY" else "short"
    
    if real_run and not await check_position_limit():
        log(f"[{symbol}] ⚠️ Maximum positions limit ({trading_config.max_positions}) reached - skipping", level="WARNING")
        return

    if dry_run:
        log(f"[{symbol}] 🧪 DRY-RUN: Simulated {direction.upper()} position opening", level="DEBUG")
    elif real_run:
        log(f"[{symbol}] ✅ REAL position opening: {direction.upper()}", level="DEBUG")
        try:
            await open_position_async(symbol, POSITION_AMOUNT_USDC, direction)
            MAX_PNL_TRACKER[symbol] = 0.0
            log(f"[{symbol}] ✅ Position opened successfully", level="DEBUG")
        except Exception as e:
            log(f"[{symbol}] ❌ Error opening position: {e}", level="ERROR")
    else:
        log(f"[{symbol}] ❌ Neither --real-run nor --dry-run specified: no action", level="ERROR")


async def check_position_limit() -> bool:
    try:
        positions = await get_open_positions()
        current_positions = len([p for p in positions.values() if p])
        return current_positions < trading_config.max_positions
    except Exception as e:
        log(f"⚠️ Error checking position limit: {e}", level="WARNING")
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
        log(f"⚠️ Error getting position stats: {e}", level="ERROR")
        return {}


async def scan_and_trade_all_symbols(pool, symbols, real_run: bool, dry_run: bool, args=None):
    """
    Parcours tous les symboles et déclenche la stratégie en parallèle.
    """
    log("🔍 Lancement du scan indicateurs et trading en parallèle…", level="INFO")
    tasks = [handle_live_symbol(symbol, pool, real_run, dry_run, args) for symbol in symbols]
    await asyncio.gather(*tasks, return_exceptions=True)