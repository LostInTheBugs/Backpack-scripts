import os
import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone

from utils.logger import log
from utils.ohlcv_utils import get_ohlcv_df
from utils.position_utils import position_already_open
from utils.public import (
    get_ohlcv,
    check_table_and_fresh_data,
    load_symbols_from_file
)
from utils.get_market import get_market
from ScriptDatabase.pgsql_ohlcv import fetch_ohlcv_1s
from signals.macd_rsi_breakout import get_combined_signal
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent

# === Configuration ===
INTERVAL = "1s"
POSITION_AMOUNT_USDC = 25
TRAILING_STOP_TRIGGER = 0.5  # Seuil de déclenchement du stop suiveur

# === Suivi du PnL maximum par symbole ===
MAX_PNL_TRACKER = {}

async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        # Vérifie si les données OHLCV sont fraîches en BDD
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            log(f"[{symbol}] Ignoré : pas de données récentes")
            return

        # === Chargement des données OHLCV ===
        if INTERVAL == "1s":
            end_ts = datetime.now(timezone.utc)
            start_ts = end_ts - timedelta(seconds=60)
            df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)

            if df is None or df.empty:
                log(f"[{symbol}] ❌ Données OHLCV 1s vides depuis PostgreSQL")
                return
        else:
            data = get_ohlcv(symbol, INTERVAL)
            if not data:
                log(f"[{symbol}] ❌ Données OHLCV vides depuis l'API Backpack")
                return
            df = get_ohlcv_df(symbol, INTERVAL)

        # === Nettoyage et vérifications ===
        if df.empty or len(df) < 2:
            log(f"[{symbol}] ⚠️ Pas assez de données pour calculer le signal")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)

        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        # === Analyse du signal ===
        signal = get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal détecté : {signal}")

        # === Vérification d'une position déjà ouverte ===
        if position_already_open(symbol):
            market_data = await get_market(symbol)
            if not market_data:
                return

            pnl_percent = market_data.get("pnl", 0.0)
            if symbol not in MAX_PNL_TRACKER:
                MAX_PNL_TRACKER[symbol] = pnl_percent

            if pnl_percent > MAX_PNL_TRACKER[symbol]:
                MAX_PNL_TRACKER[symbol] = pnl_percent

            if MAX_PNL_TRACKER[symbol] - pnl_percent >= TRAILING_STOP_TRIGGER:
                log(f"[{symbol}] ⛔ Stop suiveur déclenché : PnL {pnl_percent:.2f}% < Max {MAX_PNL_TRACKER[symbol]:.2f}% - {TRAILING_STOP_TRIGGER}%")
                if real_run:
                    close_position_percent(symbol, percent=100)
                else:
                    log(f"[{symbol}] 🧪 DRY-RUN: Clôture simulée via trailing stop")
                del MAX_PNL_TRACKER[symbol]
                return
            else:
                log(f"[{symbol}] 🔄 PnL actuel: {pnl_percent:.2f}% | Max: {MAX_PNL_TRACKER[symbol]:.2f}%")

            log(f"[{symbol}] ⚠️ Position déjà ouverte — Ignorée (sauf stop suiveur)")
            return

        # === Ouverture de position si un signal est détecté ===
        if signal in ["BUY", "SELL"]:
            direction = "long" if signal == "BUY" else "short"

            if dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Simulation d'ouverture position {direction.upper()}")
            elif real_run:
                log(f"[{symbol}] ✅ OUVERTURE position réelle : {direction.upper()}")
                open_position(symbol, POSITION_AMOUNT_USDC, direction)
            else:
                log(f"[{symbol}] ❌ Ni --real-run ni --dry-run spécifié : aucune action")

    except Exception as e:
        log(f"[{symbol}] 💥 Erreur: {e}")
        traceback.print_exc()
