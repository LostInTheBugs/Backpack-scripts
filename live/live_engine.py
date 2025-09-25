#live/live_engine.py
import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
import inspect
import asyncio
import json
import hashlib

from utils.position_utils import position_already_open, get_real_pnl, get_open_positions, safe_float
from utils.logger import log
from utils.public import check_table_and_fresh_data
from execute.async_wrappers import open_position_async, close_position_percent_async
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from signals.strategy_selector import get_strategy_for_market
from config.settings import get_config
from indicators.rsi_calculator import get_cached_rsi
from utils.table_display import handle_existing_position_with_table
from utils.position_utils import PositionTracker, get_real_positions
from utils.i18n import t

trackers = {}  # symbol -> PositionTracker

# Load configuration
config = get_config()
trading_config = config.trading

INTERVAL = "1s"
POSITION_AMOUNT_USDC = trading_config.position_amount_usdc
LEVERAGE = trading_config.leverage
TRAILING_STOP_TRIGGER = trading_config.trailing_stop_trigger
MIN_PNL_FOR_TRAILING = trading_config.min_pnl_for_trailing

MAX_PNL_TRACKER = {}  # Tracker for max PnL per symbol

# ✅ CORRECTION: Stockage amélioré avec hash stable
TRAILING_STOPS = {}  # {position_hash: {'value': float, 'max_pnl': float, 'active': bool, 'symbol': str, 'side': str}}

public_key = config.bpx_bot_public_key or os.environ.get("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.environ.get("bpx_bot_secret_key")

def get_position_hash(symbol, side, entry_price, amount):
    """
    ✅ CORRECTION: Génère un hash unique et stable pour chaque position
    """
    # Arrondir pour éviter les variations de précision
    rounded_entry = round(float(entry_price), 8)
    rounded_amount = round(float(amount), 6)
    
    position_data = f"{symbol}_{side}_{rounded_entry}_{rounded_amount}"
    return hashlib.md5(position_data.encode()).hexdigest()[:16]

async def get_position_trailing_stop(symbol, side, entry_price, mark_price, amount):
    """
    ✅ FIXED: Corrected trailing stop calculation and logic
    """
    try:
        # Generate stable hash
        position_hash = get_position_hash(symbol, side, entry_price, amount)
        
        # Calculate current PnL
        entry_p = safe_float(entry_price, 0.0)
        mark_p = safe_float(mark_price, 0.0)
        
        if entry_p <= 0 or mark_p <= 0:
            log(f"❌ [{symbol}] Invalid prices: entry={entry_p}, mark={mark_p}", level="ERROR")
            return None
            
        if side.lower() == "long":
            pnl_pct = ((mark_p - entry_p) / entry_p) * 100
        else:  # SHORT
            pnl_pct = ((entry_p - mark_p) / entry_p) * 100
        
        # Initialize tracker if not exists
        if position_hash not in TRAILING_STOPS:
            TRAILING_STOPS[position_hash] = {
                'value': None,
                'max_pnl': pnl_pct,
                'active': False,
                'symbol': symbol,
                'side': side.lower()
            }
            log(f"🆕 [{symbol}] New trailing stop tracker created - Hash: {position_hash[:8]}", level="DEBUG")
        
        tracker = TRAILING_STOPS[position_hash]
        
        # ✅ CORRECTION: Update max PnL only if current PnL is higher
        if pnl_pct > tracker['max_pnl']:
            old_max = tracker['max_pnl']
            tracker['max_pnl'] = pnl_pct
            log(f"📈 [{symbol}] Hash:{position_hash[:8]} Max PnL updated: {old_max:.2f}% → {pnl_pct:.2f}%", level="INFO")
        
        # ✅ ACTIVATION: Enable trailing stop when reaching minimum PnL
        if not tracker['active'] and pnl_pct >= MIN_PNL_FOR_TRAILING:
            tracker['active'] = True
            tracker['value'] = tracker['max_pnl'] - TRAILING_STOP_TRIGGER
            log(f"🟢 [{symbol}] TRAILING STOP ACTIVATED! PnL: {pnl_pct:.2f}% ≥ {MIN_PNL_FOR_TRAILING}% → Trailing: {tracker['value']:.2f}%", level="WARNING")
            return tracker['value']
        
        # ✅ UPDATE: Adjust trailing stop if already active
        if tracker['active']:
            # Calculate new trailing stop based on max PnL
            new_trailing = tracker['max_pnl'] - TRAILING_STOP_TRIGGER
            
            # ✅ CORRECTION: Trailing stop can only move up (for protection)
            if new_trailing > tracker['value']:
                old_trailing = tracker['value']
                tracker['value'] = new_trailing
                log(f"🔼 [{symbol}] Trailing updated: {old_trailing:.2f}% → {tracker['value']:.2f}%", level="INFO")
            
            return tracker['value']
        
        # Not active yet
        return None
        
    except Exception as e:
        log(f"❌ Error in get_position_trailing_stop for {symbol}: {e}", level="ERROR")
        return None

def handle_live_symbol(symbol, current_price, side, entry_price, amount):
    if symbol not in trackers:
        trackers[symbol] = PositionTracker(symbol, side, entry_price, amount, trailing_percent=1.0)

    tracker = trackers[symbol]
    tracker.update_price(current_price)
    pnl_usd, pnl_percent = tracker.get_unrealized_pnl(current_price)
    trailing = tracker.get_trailing_stop()

    return {
        "symbol": symbol,
        "side": side,
        "pnl_usd": pnl_usd,
        "pnl_percent": pnl_percent,
        "trailing_stop": trailing
    }

async def scan_all_symbols(pool, symbols):
    log(t("live_engine.scan.launch"), level="INFO")
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
            log(t("live_engine.scan.unexpected_result", result=res), level="WARNING")

    log(t("live_engine.scan.ok_symbols", symbols=ok_symbols), level="DEBUG")
    log(t("live_engine.scan.ko_symbols", symbols=ko_symbols), level="DEBUG")
    log(t("live_engine.scan.summary", ok_count=len(ok_symbols), ko_count=len(ko_symbols), total=len(symbols)), level="DEBUG")

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
    required_cols = ["EMA20", "EMA50", "EMA200", "RSI", "MACD"]
    for period, col in [(20,"EMA20"),(50,"EMA50"),(200,"EMA200")]:
        if col not in df.columns:
            df[col] = df['close'].ewm(span=period, adjust=False).mean()

    try:
        rsi_value = await get_cached_rsi(symbol, interval="5m")
        df['RSI'] = rsi_value
        log(t("live_engine.indicators.rsi_retrieved", symbol=symbol, rsi=rsi_value), level="DEBUG")
    except Exception as e:
        log(t("live_engine.indicators.rsi_error_fallback", symbol=symbol, error=e), level="WARNING")
        try:
            from indicators.rsi_calculator import calculate_rsi
            rsi_value = calculate_rsi(df['close'], period=14)
            df['RSI'] = rsi_value
            log(t("live_engine.indicators.rsi_calculated", symbol=symbol, rsi=rsi_value.iloc[-1]), level="DEBUG")
        except Exception as e2:
            df['RSI'] = 50
            log(t("live_engine.indicators.rsi_failed", symbol=symbol, error=e2), level="ERROR")

    if 'MACD' not in df.columns or 'MACD_signal' not in df.columns:
        short_window, long_window, signal_window = 12,26,9
        ema_short = df['close'].ewm(span=short_window, adjust=False).mean()
        ema_long = df['close'].ewm(span=long_window, adjust=False).mean()
        df['MACD'] = ema_short - ema_long
        df['MACD_signal'] = df['MACD'].ewm(span=signal_window, adjust=False).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
        log(t("live_engine.indicators.macd_calculated", symbol=symbol), level="DEBUG")

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        log(t("live_engine.indicators.missing", symbol=symbol, missing=missing), level="WARNING")
        return None

    for col in required_cols:
        if col != 'RSI' and df[col].isna().any():
            log(t("live_engine.indicators.nan_detected", symbol=symbol, column=col), level="WARNING")
            return None

    return df

def should_close_position(pnl_pct, trailing_stop, side, duration_sec, strategy=None):
    """
    ✅ CORRECTION: Logique de fermeture avec activation immédiate des trailing stops
    """
    
    # ✅ CAS 1: TRAILING STOP ACTIVÉ - Fermer IMMÉDIATEMENT si PnL <= trailing stop
    if trailing_stop is not None:
        if pnl_pct <= trailing_stop:
            log(f"🚨 [{side.upper()}] TRAILING STOP TRIGGERED: PnL {pnl_pct:.2f}% ≤ Trailing {trailing_stop:.2f}% → IMMEDIATE CLOSE", level="WARNING")
            return True
        else:
            log(f"✅ [{side.upper()}] Trailing safe: PnL {pnl_pct:.2f}% > Trailing {trailing_stop:.2f}%", level="DEBUG")
            return False
    
    # ✅ CAS 2: TRAILING STOP PAS ENCORE ACTIVÉ - Stop loss fixe IMMÉDIAT (pas de durée minimale)
    
    try:
        current_strategy = strategy or config.strategy.default_strategy.lower()
        
        # Stop-loss plus agressif basé sur votre préférence
        if "threeoutoffour" in current_strategy or "three_out_of_four" in current_strategy:
            stop_loss_pct = -config.strategy.three_out_of_four.stop_loss_pct
        elif "twooutoffourscalp" in current_strategy or "two_out_of_four_scalp" in current_strategy:
            stop_loss_pct = -config.strategy.two_out_of_four_scalp.stop_loss_pct
        else:
            # VOTRE PRÉFÉRENCE : Stop-loss à -2%
            stop_loss_pct = -2.0
        
        if pnl_pct <= stop_loss_pct:
            log(f"🔴 [{side.upper()}] FIXED STOP LOSS: PnL {pnl_pct:.2f}% ≤ Stop {stop_loss_pct:.2f}% → CLOSE POSITION", level="WARNING")
            return True
            
    except Exception as e:
        log(f"❌ Stop loss check error: {e} - Using default -2%", level="ERROR")
        if pnl_pct <= -2.0:
            log(f"🔴 [{side.upper()}] DEFAULT STOP LOSS: PnL {pnl_pct:.2f}% ≤ -2.0% → CLOSE POSITION", level="WARNING")
            return True
    
    return False

async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool, args=None):
    try:
        log(t("live_engine.data.loading", symbol=symbol, interval=INTERVAL), level="DEBUG")
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
            log(t("live_engine.data.no_recent", symbol=symbol), level="ERROR")
            return

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=600)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts, pool=pool)
        if df is None or df.empty:
            log(t("live_engine.data.no_1s_data", symbol=symbol), level="ERROR")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)

        if args.strategie == "Auto":
            market_condition, selected_strategy = get_strategy_for_market(df)
            log(t("live_engine.strategy.market_detected", symbol=symbol, condition=market_condition.upper(), strategy=selected_strategy), level="DEBUG")
        else:
            selected_strategy = args.strategie
            log(t("live_engine.strategy.manual_selected", symbol=symbol, strategy=selected_strategy), level="DEBUG")

        get_combined_signal = import_strategy_signal(selected_strategy)
        
        df_result = await ensure_indicators(df, symbol)
        
        if asyncio.iscoroutine(df_result):
            log(t("live_engine.debug.awaiting_coroutine", symbol=symbol), level="DEBUG")
            df = await df_result
        else:
            df = df_result
            
        if df is None:
            log(t("live_engine.indicators.calculation_failed", symbol=symbol), level="ERROR")
            return

        if not isinstance(df, pd.DataFrame):
            log(t("live_engine.data.dataframe_error", symbol=symbol, type=type(df)), level="ERROR")
            return
            
        if df.empty:
            log(t("live_engine.data.dataframe_empty", symbol=symbol), level="WARNING")
            return

        try:
            if inspect.iscoroutinefunction(get_combined_signal):
                log(t("live_engine.strategy.calling_async", symbol=symbol), level="DEBUG")
                result = await get_combined_signal(df, symbol)
            else:
                log(t("live_engine.strategy.calling_sync", symbol=symbol), level="DEBUG")
                result = get_combined_signal(df, symbol)
                
            log(t("live_engine.strategy.returned", symbol=symbol, type=type(result), result=result), level="DEBUG")
            
        except Exception as e:
            log(t("live_engine.strategy.error", symbol=symbol, error=e), level="ERROR")
            traceback.print_exc()
            return

        if isinstance(result, (tuple, list)) and len(result) == 2:
            signal, details = result
        else:
            signal = result
            details = {}

        log(t("live_engine.signals.detected", symbol=symbol, signal=signal, details=details), level="DEBUG")

        # ✅ CORRECTION: UN SEUL APPEL à position_already_open
        position_exists = await position_already_open(symbol)
        log(f"[MAIN LOOP] {symbol} position_already_open: {position_exists}", level="INFO")
        
        if position_exists:
            # ✅ CORRECTION: Appel direct à la fonction corrigée
            await handle_existing_position(symbol, real_run, dry_run)
            # ✅ Alternative si vous voulez garder l'affichage tableau
            # await handle_existing_position_with_table(symbol, real_run, dry_run)
            return

        if signal in ["BUY","SELL"]:
            await handle_new_position(symbol, signal, real_run, dry_run)
            log(t("live_engine.signals.try_open", symbol=symbol, signal=signal), level="DEBUG")
        else:
            log(t("live_engine.signals.no_actionable", symbol=symbol, signal=signal), level="DEBUG")

    except Exception as e:
        log(t("live_engine.errors.generic", symbol=symbol, error=e), level="ERROR")
        traceback.print_exc()

def parse_position(pos):
    """Convertit la position en dict si JSON valide, sinon None."""
    if isinstance(pos, dict):
        return pos
    elif isinstance(pos, str):
        pos = pos.strip()
        if not pos:
            return None
        try:
            return json.loads(pos)
        except json.JSONDecodeError:
            return None
    return None

async def handle_existing_position(symbol, real_run=True, dry_run=False):
    """
    ✅ CORRECTION MAJEURE: Gestion des positions existantes avec trailing stop corrigé
    """
    try:
        # Récupération des positions réelles
        raw_positions = await get_real_positions()
        parsed_positions = [parse_position(p) for p in raw_positions if parse_position(p) is not None]

        pos = next((p for p in parsed_positions if p["symbol"] == symbol), None)
        if not pos:
            log(f"⚠️ [{symbol}] No valid position found", level="WARNING")
            return

        # ✅ CORRECTION: Extraction sécurisée des données
        side = pos.get("side")
        entry_price = safe_float(pos.get("entry_price"), 0.0)
        amount = safe_float(pos.get("amount"), 0.0)
        leverage = safe_float(pos.get("leverage", 1), 1.0)
        ts = safe_float(pos.get("timestamp", datetime.utcnow().timestamp()), datetime.utcnow().timestamp())

        if entry_price <= 0 or amount <= 0:
            log(f"❌ [{symbol}] Invalid position data: entry_price={entry_price}, amount={amount}", level="ERROR")
            return

        # Calcul du PnL réel
        pnl_data = await get_real_pnl(symbol, side, entry_price, amount, leverage)
        
        if isinstance(pnl_data, dict):
            pnl_usdc = safe_float(pnl_data.get("pnl_usd", 0), 0.0)
            pnl_percent = safe_float(pnl_data.get("pnl_percent", 0), 0.0)
            mark_price = safe_float(pnl_data.get("mark_price", entry_price), entry_price)
        else:
            log(f"⚠️ [{symbol}] Unexpected PnL data type: {type(pnl_data)}", level="WARNING")
            pnl_usdc = 0.0
            pnl_percent = 0.0
            mark_price = entry_price

        pnl_pct = safe_float(pnl_percent, 0.0)

        # ✅ CORRECTION: Appel corrigé du trailing stop avec tous les paramètres
        trailing_stop = await get_position_trailing_stop(symbol, side, entry_price, mark_price, amount)

        duration_sec = datetime.utcnow().timestamp() - ts
        duration_str = f"{int(duration_sec // 3600)}h{int((duration_sec % 3600) // 60)}m"

        # ✅ LOG DE DEBUG POUR COMPRENDRE LE PROBLÈME
        log(f"🔍 [{symbol}] CLOSE CHECK: PnL={pnl_pct:.2f}%, Trailing={trailing_stop}, Duration={duration_sec}s, ShouldClose=?", level="INFO")

        # Vérification de fermeture
        should_close = should_close_position(pnl_pct, trailing_stop, side, duration_sec, strategy=config.strategy.default_strategy)
        
        log(f"🔍 [{symbol}] CLOSE CHECK: PnL={pnl_pct:.2f}%, Trailing={trailing_stop}, Duration={duration_sec}s, ShouldClose={should_close}", level="INFO")
        
        if should_close:
            if real_run:
                try:
                    close_reason = 'Trailing Stop Hit' if trailing_stop is not None else 'Fixed Stop Loss'
                    log(f"🚨 [{symbol}] CLOSING POSITION - Reason: {close_reason}", level="WARNING")
                    
                    await close_position_percent_async(symbol, 100)
                    
                    # Nettoyage du trailing stop
                    position_hash = get_position_hash(symbol, side, entry_price, amount)
                    if position_hash in TRAILING_STOPS:
                        del TRAILING_STOPS[position_hash]
                        log(f"🧹 [{symbol}] Trailing tracker cleaned (Hash: {position_hash[:8]})", level="INFO")
                    
                    log(f"✅ [{symbol}] Position closed successfully", level="INFO")
                    
                except Exception as e:
                    log(f"❌ [{symbol}] Error closing position: {e}", level="ERROR")
            elif dry_run:
                log(f"🔄 [{symbol}] DRY RUN: Would close position immediately", level="INFO")

    except Exception as e:
        log(f"❌ [{symbol}] Position handling error: {e}", level="ERROR")
        traceback.print_exc()

async def handle_new_position(symbol: str, signal: str, real_run: bool, dry_run: bool):
    direction = "long" if signal=="BUY" else "short"
    
    if real_run and not await check_position_limit():
        log(t("live_engine.positions.limit_reached", symbol=symbol, max=trading_config.max_positions), level="WARNING")
        return

    if dry_run:
        log(t("live_engine.positions.opening_dry", symbol=symbol, direction=direction.upper()), level="DEBUG")
    elif real_run:
        log(t("live_engine.positions.opening_real", symbol=symbol, direction=direction.upper()), level="DEBUG")
        try:
            await open_position_async(symbol, POSITION_AMOUNT_USDC, direction)
            MAX_PNL_TRACKER[symbol] = 0.0
            log(t("live_engine.positions.opened_success", symbol=symbol), level="DEBUG")
        except Exception as e:
            log(t("live_engine.positions.open_error", symbol=symbol, error=e), level="ERROR")
    else:
        log(t("live_engine.positions.neither_run_mode", symbol=symbol), level="ERROR")

async def check_position_limit() -> bool:
    try:
        positions = await get_open_positions()
        current_positions = len([p for p in positions.values() if p])
        return current_positions < trading_config.max_positions
    except Exception as e:
        log(t("live_engine.errors.position_limit", error=e), level="WARNING")
        return True

async def get_position_stats() -> dict:
    try:
        positions = await get_open_positions()
        return {
            'total_positions': len([p for p in positions.values() if p]),
            'max_positions': trading_config.max_positions,
            'position_amount': POSITION_AMOUNT_USDC,
            'leverage': LEVERAGE,
            '_trigger': TRAILING_STOP_TRIGGER,
            'min_pnl_for_trailing': MIN_PNL_FOR_TRAILING
        }
    except Exception as e:
        log(t("live_engine.errors.position_stats", error=e), level="ERROR")
        return {}

# ✅ NOUVELLE FONCTION DE DEBUG
def debug_trailing_stops():
    """Affiche l'état de tous les trailing stops actifs pour debug"""
    if not TRAILING_STOPS:
        log("🔍 No active trailing stops tracked", level="DEBUG")
        return
        
    log(f"🔍 Active Trailing Stops ({len(TRAILING_STOPS)} total):", level="INFO")
    for hash_key, data in TRAILING_STOPS.items():
        status = "🟢 ACTIVE" if data['active'] else "⏳ WAITING"
        symbol = data.get('symbol', 'UNKNOWN')
        side = data.get('side', 'UNKNOWN')
        max_pnl = data.get('max_pnl', 0)
        trailing_val = data.get('value', 'N/A')
        log(f"  {status} [{symbol}] {side.upper()} Hash:{hash_key[:8]} | Max PnL: {max_pnl:.2f}% | Trailing: {trailing_val}", level="INFO")

async def scan_and_trade_all_symbols(pool, symbols, real_run: bool, dry_run: bool, args=None):
    """
    ✅ CORRECTION: Parcours avec debug des trailing stops
    """
    log("🔍 Lancement du scan indicateurs et trading en parallèle…", level="INFO")
    
    # ✅ AJOUT: Debug des trailing stops avant chaque cycle
    debug_trailing_stops()
    
    tasks = [handle_live_symbol(symbol, pool, real_run, dry_run, args) for symbol in symbols]
    await asyncio.gather(*tasks, return_exceptions=True)

