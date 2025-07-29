import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone
import os

from utils.ohlcv_utils import get_ohlcv_df
from utils.position_utils import position_already_open
from utils.logger import log
from utils.public import format_table_name, check_table_and_fresh_data
from utils.get_market import get_market
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from utils.position_utils import get_real_pnl

INTERVAL = "1s"
POSITION_AMOUNT_USDC = 25
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
    else:
        from signals.macd_rsi_breakout import get_combined_signal
    return get_combined_signal



async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool, args):
    get_combined_signal = import_strategy_signal(args.strategie)
    print(f"📊 Stratégie sélectionnée : {args.strategie}")
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        # Vérifie que la table locale a des données récentes (moins de 60s)
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            log(f"[{symbol}] Ignoré : pas de données récentes dans la BDD locale")
            return

        # Récupère OHLCV 1s depuis la BDD locale
        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(seconds=60)
        df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)

        if df is None or df.empty:
            log(f"[{symbol}] ❌ Pas de données 1s récupérées depuis la BDD locale")
            return

        # Préparation DataFrame
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        # Calcul du signal
        signal = args.get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal détecté : {signal}")

        # Gestion position ouverte
        if position_already_open(symbol):
            #arket_data = await get_market(symbol)
            #f not market_data:
            #   log(f"[{symbol}] ⚠️ Données marché non trouvées, stop trailing ignoré")
            #   return

            #nl_percent = market_data.get("pnl", 0.0)
            pnl_usdc = await get_real_pnl(symbol)
            pnl_percent = (pnl_usdc / POSITION_SIZE_USDC) * 100

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

        # Pas de position ouverte : exécution si signal BUY ou SELL
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
