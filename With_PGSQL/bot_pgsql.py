import argparse
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
import pandas as pd

from With_PGSQL.pgsql_ohlcv import get_ohlcv_1s_sync
from utils.logger import log
from signals.macd_rsi_breakout import get_combined_signal
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from backpack_public.get_market import get_market
from utils.position_utils import position_already_open
from utils.ohlcv_utils import get_ohlcv_df
from fetch_top_volume_symbols import fetch_top_n_perp
from backpack_public.public import get_ohlcv

POSITION_AMOUNT_USDC = 25
INTERVAL = "1m"
public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

def handle_live_symbol(symbol: str, real_run: bool, dry_run: bool):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")
        data = get_ohlcv(symbol, INTERVAL)

        if not data:
            log(f"[{symbol}] ❌ Données OHLCV vides")
            return

        df = get_ohlcv_df(symbol, INTERVAL)

        if df.empty:
            log(f"[{symbol}] ❌ DataFrame OHLCV vide après conversion")
            return

        signal = get_combined_signal(df)
        log(f"[{symbol}] 🎯 Signal détecté : {signal}")

        if signal in ["BUY", "SELL"]:
            if position_already_open(symbol):
                log(f"[{symbol}] ⚠️ Position déjà ouverte — Ignorée")
                return

            if dry_run:
                log(f"[{symbol}] 🧪 DRY-RUN: Simulation d'ouverture position {signal}")
            elif real_run:
                log(f"[{symbol}] ✅ OUVERTURE position réelle : {signal}")
                open_position(symbol, POSITION_AMOUNT_USDC, signal, public_key, secret_key)
            else:
                log(f"[{symbol}] ❌ Ni --real-run ni --dry-run spécifié : aucune action")
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur: {e}")
        traceback.print_exc()

def backtest_symbol(symbol: str, interval: str):
    from backtest.backtest_engine import run_backtest  # à adapter selon ton structure
    try:
        log(f"[{symbol}] 🧪 Lancement du backtest en {interval}")
        run_backtest(symbol, interval)
    except Exception as e:
        log(f"[{symbol}] 💥 Erreur durant le backtest: {e}")
        traceback.print_exc()

def load_symbols_from_file(filepath: str = "symbol.lst") -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]

def main_loop(symbols: list, real_run: bool, dry_run: bool, auto_select=False):
    if auto_select:
        log("🔍 Mode auto-select actif — sélection des symboles les plus volatils")
        try:
            symbols = fetch_top_n_perp(n=len(symbols))
            log(f"✅ Symboles sélectionnés automatiquement : {symbols}")
        except Exception as e:
            log(f"💥 Erreur sélection symboles auto: {e}")
            return

    for symbol in symbols:
        handle_live_symbol(symbol, real_run, dry_run)

def watch_symbols_file(filepath: str = "symbol.lst", real_run: bool = False, dry_run: bool = False):
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                symbols = load_symbols_from_file(filepath)
                log(f"🔁 symbol.lst rechargé : {symbols}")
                last_modified = current_modified

            main_loop(symbols, real_run=real_run, dry_run=dry_run)
        except KeyboardInterrupt:
            log("🛑 Arrêt manuel demandé")
            break
        except Exception as e:
            log(f"💥 Erreur dans le watcher : {e}")
            traceback.print_exc()

        time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Liste des symboles (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation sans exécuter de trade")
    parser.add_argument("--backtest", type=str, help="Exécuter un backtest (ex: 1h, 1d, 1w)")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symboles les plus volatils")

    args = parser.parse_args()

    if args.backtest:
        if args.symbols:
            symbols = args.symbols.split(",")
        else:
            symbols = load_symbols_from_file()

        for symbol in symbols:
            backtest_symbol(symbol, args.backtest)
    else:
        if args.symbols:
            symbols = args.symbols.split(",")
            main_loop(symbols, real_run=args.real_run, dry_run=args.dry_run, auto_select=args.auto_select)
        else:
            watch_symbols_file(real_run=args.real_run, dry_run=args.dry_run)
