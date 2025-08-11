import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
import os

from utils.position_utils import position_already_open
from utils.logger import log
from utils.public import check_table_and_fresh_data
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from utils.position_utils import get_real_pnl
from signals.strategy_selector import get_strategy_for_market
from config.settings import get_config

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

def import_strategy_signal(strategy):
    """Import strategy signal function dynamically"""
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
    else:
        from signals.macd_rsi_breakout import get_combined_signal
    return get_combined_signal

async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool, args):
    """Handle live trading for a single symbol"""
    try:
        log(f"[{symbol}] 📈 Loading OHLCV data for {INTERVAL}")

        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
            log(f"[{symbol}] ❌ Ignored: no recent data in local database")
            return

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=60)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)

        if df is None or df.empty:
            log(f"[{symbol}] ❌ No 1s data retrieved from local database")
            return

        # Prepare DataFrame
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        # Strategy selection (dynamic or manual)
        if args.strategie == "Auto":
            market_condition, selected_strategy = get_strategy_for_market(df)
            log(f"[{symbol}] 📊 Market detected: {market_condition.upper()} — Strategy selected: {selected_strategy}")
        else:
            selected_strategy = args.strategie
            log(f"[{symbol}] 📊 Strategy manually selected: {selected_strategy}")

        get_combined_signal = import_strategy_signal(selected_strategy)
        signal = get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal detected: {signal}")

        # Handle existing positions with trailing stop
        if position_already_open(symbol):
            await handle_existing_position(symbol, real_run, dry_run)
            return

        # Handle new position signals
        if signal in ["BUY", "SELL"]:
            await handle_new_position(symbol, signal, real_run, dry_run)
            log("[DEBUG] {symbol} 🚨 Try open position: {signal}", level="DEBUG")
        else:
            log("[DEBUG] {symbol} ❌ No actionable signal detected: {signal}", level="DEBUG")

    except Exception as e:
        log(f"[{symbol}] 💥 Error: {e}")
        traceback.print_exc()

async def handle_existing_position(symbol: str, real_run: bool, dry_run: bool):
    """Handle existing position with trailing stop logic"""
    pnl_usdc, notional_value = get_real_pnl(symbol)
    pnl_percent = (pnl_usdc / (POSITION_AMOUNT_USDC / LEVERAGE)) * 100

    # Update max PnL tracker
    max_pnl = MAX_PNL_TRACKER.get(symbol, pnl_percent)
    if pnl_percent > max_pnl:
        MAX_PNL_TRACKER[symbol] = pnl_percent
        max_pnl = pnl_percent

    # Check trailing stop only if we have minimum profit
    if max_pnl >= MIN_PNL_FOR_TRAILING and (max_pnl - pnl_percent) >= TRAILING_STOP_TRIGGER:
        log(f"[{symbol}] ⛔ Trailing stop triggered: PnL {pnl_percent:.2f}% < Max {max_pnl:.2f}% - {TRAILING_STOP_TRIGGER}%")
        
        if real_run:
            try:
                close_position_percent(public_key, secret_key, symbol, percent=100)
                log(f"[{symbol}] ✅ Position closed successfully via trailing stop")
            except Exception as e:
                log(f"[{symbol}] ❌ Error closing position: {e}")
        else:
            log(f"[{symbol}] 🧪 DRY-RUN: Simulated close via trailing stop")
        
        # Reset tracker
        MAX_PNL_TRACKER.pop(symbol, None)
        return
    else:
        log(f"[{symbol}] 🔄 Current PnL: {pnl_percent:.2f}% | Max: {max_pnl:.2f}% | Min for trailing: {MIN_PNL_FOR_TRAILING:.1f}%")
        MAX_PNL_TRACKER[symbol] = max_pnl

    log(f"[{symbol}] ⚠️ Position already open — Monitoring (trailing stop active)")

async def handle_new_position(symbol: str, signal: str, real_run: bool, dry_run: bool):
    """Handle new position opening"""
    direction = "long" if signal == "BUY" else "short"
    
    # Check maximum positions limit
    if real_run and not check_position_limit():
        log(f"[{symbol}] ⚠️ Maximum positions limit ({trading_config.max_positions}) reached - skipping")
        return
    
    if dry_run:
        log(f"[{symbol}] 🧪 DRY-RUN: Simulated {direction.upper()} position opening")
    elif real_run:
        log(f"[{symbol}] ✅ REAL position opening: {direction.upper()}")
        try:
            open_position(symbol, POSITION_AMOUNT_USDC, direction)
            # Initialize PnL tracker for new position
            MAX_PNL_TRACKER[symbol] = 0.0
            log(f"[{symbol}] ✅ Position opened successfully")
        except Exception as e:
            log(f"[{symbol}] ❌ Error opening position: {e}")
    else:
        log(f"[{symbol}] ❌ Neither --real-run nor --dry-run specified: no action")

def check_position_limit() -> bool:
    """Check if we can open a new position based on max_positions limit"""
    try:
        from utils.position_utils import get_open_positions
        positions = get_open_positions()
        current_positions = len([p for p in positions.values() if p])
        return current_positions < trading_config.max_positions
    except Exception as e:
        log(f"⚠️ Error checking position limit: {e}")
        return True  # Allow trading if we can't check (fail-safe)

def get_position_stats() -> dict:
    """Get current position statistics"""
    try:
        from utils.position_utils import get_open_positions
        positions = get_open_positions()
        
        stats = {
            'total_positions': len([p for p in positions.values() if p]),
            'max_positions': trading_config.max_positions,
            'position_amount': POSITION_AMOUNT_USDC,
            'leverage': LEVERAGE,
            'trailing_stop_trigger': TRAILING_STOP_TRIGGER,
            'min_pnl_for_trailing': MIN_PNL_FOR_TRAILING
        }
        return stats
    except Exception as e:
        log(f"⚠️ Error getting position stats: {e}")
        return {}