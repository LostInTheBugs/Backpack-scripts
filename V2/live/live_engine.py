import os
import traceback
import pandas as pd
from datetime import datetime, timedelta, timezone

from utils.ohlcv_utils import get_ohlcv_df
from utils.position_utils import position_already_open
from utils.logger import log
from utils.public import get_ohlcv, format_table_name, check_table_and_fresh_data, fetch_ohlcv_1s
from utils.get_market import get_market
from signals.macd_rsi_breakout import get_combined_signal
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent

INTERVAL = "1s"
POSITION_AMOUNT_USDC = 25
TRAILING_STOP_TRIGGER = 0.5  # stop si le PnL baisse de 0.5% depuis le max

MAX_PNL_TRACKER = {}  # Dictionnaire pour stocker le PnL max atteint par symbole

async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        # Vérifie que la table locale a des données fraîches
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            log(f"[{symbol}] Ignoré : pas de données récentes dans la BDD locale")
            return

        # --- Récupération des données OHLCV ---
        if INTERVAL == "1s":
            # Utilise uniquement la BDD locale pour 1s
            end_ts = datetime.now(timezone.utc)
            start_ts = end_ts - timedelta(seconds=60)
            df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
            if df is None or df.empty:
                log(f"[{symbol}] ❌ Pas de données 1s récupérées depuis la BDD locale")
                return
        else:
            # Pour les autres intervalles, utilise l'API Backpack uniquement
            data = get_ohlcv(symbol, INTERVAL)
            if not data:
                log(f"[{symbol}] ❌ Données OHLCV vides ou erreur API")
                return
            df = get_ohlcv_df(symbol, INTERVAL)
            if df is None or df.empty:
                log(f"[{symbol}] ❌ DataFrame OHLCV vide après conversion")
                return

        # Préparation DataFrame
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        df.set_index('timestamp', inplace=True)

        # Conversion des colonnes importantes en float
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

        # Calcul du signal (ex: MACD + RSI breakout)
        signal = get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal détecté : {signal}")

        # Vérifie si une position est déjà ouverte
        if position_already_open(symbol):
            # Gestion du trailing stop par PnL
            market_data = await get_market(symbol)
            if not market_data:
                log(f"[{symbol}] ⚠️ Données marché non trouvées, stop trailing ignoré")
                return

            pnl_percent = market_data.get("pnl", 0.0)
            if symbol not in MAX_PNL_TRACKER:
                MAX_PNL_TRACKER[symbol] = pnl_percent

            if pnl_percent > MAX_PNL_TRACKER[symbol]:
                MAX_PNL_TRACKER[symbol] = pnl_percent

            if MAX_PNL_TRACKER[symbol] - pnl_percent >= TRAILING_STOP_TRIGGER:
                log(f"[{symbol}] ⛔ Stop suiveur déclenché : PnL {pnl_percent:.2f}% < Max {MAX_PNL_TRACKER[symbol]:.2f}% - {TRAILING_STOP_TRIGGER}%")
                if real_run:
                    await close_position_percent(symbol, percent=100)
                else:
                    log(f"[{symbol}] 🧪 DRY-RUN: Clôture simulée via trailing stop")
                del MAX_PNL_TRACKER[symbol]
                return
            else:
                log(f"[{symbol}] 🔄 PnL actuel: {pnl_percent:.2f}% | Max: {MAX_PNL_TRACKER[symbol]:.2f}%")

            log(f"[{symbol}] ⚠️ Position déjà ouverte — Ignorée (sauf stop suiveur)")
            return

        # Pas de position ouverte, on regarde le signal
        if signal in ["BUY", "SELL"]:
            direction = "long" if signal == "BUY" else "short"

            if dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Simulation ouverture position {direction.upper()}")
            elif real_run:
                log(f"[{symbol}] ✅ OUVERTURE position réelle : {direction.upper()}")
                await open_position(symbol, POSITION_AMOUNT_USDC, direction)
            else:
                log(f"[{symbol}] ❌ Ni --real-run ni --dry-run spécifié : aucune action")

    except Exception as e:
        log(f"[{symbol}] 💥 Erreur: {e}")
        traceback.print_exc()
