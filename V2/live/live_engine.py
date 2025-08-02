import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
import json

from utils.position_utils import position_already_open, get_real_pnl
from utils.logger import log
from utils.public import check_table_and_fresh_data
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from signals.strategy_selector import get_strategy_for_market

# Import fonction sauvegarde signaux en base
from utils.logger import save_signal_to_db


INTERVAL = "1s"
POSITION_AMOUNT_USDC = 50
LEVERAGE = 2
TRAILING_STOP_TRIGGER = 0.5  # stop si le PnL baisse de 0.5% depuis le max

MAX_PNL_TRACKER = {}  # Tracker du max PnL par symbole

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

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
    else:
        from signals.macd_rsi_breakout import get_combined_signal
    return get_combined_signal


async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool, args):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=600):
            log(f"[{symbol}] Ignoré : pas de données récentes dans la BDD locale")
            return

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=60)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)

        if df is None or df.empty:
            log(f"[{symbol}] ❌ Pas de données 1s récupérées depuis la BDD locale")
            return

        # Préparation df (timestamps, types...)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        # Sélection dynamique ou fixe de la stratégie
        strategy_arg = args.strategie.lower()
        if strategy_arg in ["auto", "autosoft"]:
            market_type, selected_strategy = get_strategy_for_market(df)
            log(f"[{symbol}] 📊 Marché détecté : {market_type.upper()} — Stratégie auto sélectionnée : {selected_strategy}")
        else:
            selected_strategy = args.strategie
            market_type = None
            log(f"[{symbol}] 📊 Stratégie sélectionnée manuellement : {selected_strategy}")

        get_combined_signal = import_strategy_signal(selected_strategy)

        signal = get_combined_signal(df)

        # Récupération indicateurs pour la base
        current_price = df['close'].iloc[-1]

        rsi_value = df['rsi'].iloc[-1] if 'rsi' in df.columns else None
        trix_value = df['trix'].iloc[-1] if 'trix' in df.columns else None

        # Préparer message log pour base
        log_message = f"Signal détecté ({selected_strategy}) : {signal} | Price={current_price} RSI={rsi_value} TRIX={trix_value}"

        # Sauvegarder en base
        save_signal_to_db(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            market_type=market_type,
            strategy=selected_strategy,
            signal=signal,
            price=current_price,
            rsi=rsi_value,
            trix=trix_value,
            raw_data={"msg": log_message}
        )

        # Ne PAS logger ce signal à la console pour éviter de spammer
        # log(f"[{symbol}] 🎯 {log_message}")

        # Gestion position ouverte + trailing stop
        if position_already_open(symbol):
            pnl_usdc, notional_value = get_real_pnl(symbol)
            pnl_percent = (pnl_usdc / (POSITION_AMOUNT_USDC / LEVERAGE)) * 100

            max_pnl = MAX_PNL_TRACKER.get(symbol, pnl_percent)
            if pnl_percent > max_pnl:
                MAX_PNL_TRACKER[symbol] = pnl_percent
                max_pnl = pnl_percent

            if max_pnl - pnl_percent >= TRAILING_STOP_TRIGGER:
                log(f"[{symbol}] ⛔ Stop suiveur déclenché : PnL {pnl_percent:.2f}% < Max {max_pnl:.2f}% - {TRAILING_STOP_TRIGGER}%")
                if real_run:
                    close_position_percent(public_key, secret_key, symbol, percent=100)
                else:
                    log(f"[{symbol}] 🧪 DRY-RUN: Clôture simulée via trailing stop")
                MAX_PNL_TRACKER.pop(symbol, None)
                return
            else:
                log(f"[{symbol}] 🔄 PnL actuel: {pnl_percent:.2f}% | Max: {max_pnl:.2f}%")
                MAX_PNL_TRACKER[symbol] = max_pnl

            log(f"[{symbol}] ⚠️ Position déjà ouverte — Ignorée (sauf stop suiveur)")
            return

        # Ouverture position selon signal BUY/SELL
        if signal in ["BUY", "SELL"]:
            direction = "long" if signal == "BUY" else "short"
            if dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Simulation ouverture position {direction.upper()}")
            elif real_run:
                log(f"[{symbol}] ✅ OUVERTURE position réelle : {direction.upper()}")
                open_position(symbol, POSITION_AMOUNT_USDC, direction)
            else:
                log(f"[{symbol}] ❌ Ni --real-run ni --dry-run spécifié : aucune action")

    except Exception as e:
        log(f"[{symbol}] 💥 Erreur: {e}")
        traceback.print_exc()
