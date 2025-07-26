import argparse
import os
import time
import traceback
import asyncio
from datetime import datetime, timedelta, timezone
import pandas as pd
import asyncpg
import signal
import datetime

from With_PGSQL.pgsql_ohlcv import get_ohlcv_1s_sync, fetch_ohlcv_1s
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
INTERVAL = "1s"
public_key = os.getenv("bpx_bot_public_key")
secret_key = os.getenv("bpx_bot_secret_key")

async def check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
    table_name = f"ohlcv_{symbol.lower().replace('-', '_').replace('/', '_').replace('__', '_')}"
    async with pool.acquire() as conn:
        # Vérifie si la table existe
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_name)
        if not table_exists:
            print(f"[{symbol}] ❌ Table {table_name} absente.")
            return False

        try:
            now = datetime.datetime.utcnow()  # Naïf (sans tzinfo)
            cutoff = now - datetime.timedelta(seconds=max_age_seconds)

            row = await conn.fetchrow(f"""
                SELECT timestamp FROM {table_name}
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            if not row:
                print(f"[{symbol}] ⚠️ Table présente mais aucune donnée.")
                return False
            
            last_timestamp = row['timestamp']
            if last_timestamp is None:
                print(f"[{symbol}] ⚠️ Dernier timestamp vide.")
                return False
            
            # For debug
            print(f"[{symbol}] 🕒 Dernière donnée : {last_timestamp} (cutoff: {cutoff})")

            if last_timestamp < cutoff:
                print(f"[{symbol}] ⚠️ Pas de données récentes depuis plus de {max_age_seconds} sec.")
                return False
            return True
        except Exception as e:
            print(f"[{symbol}] 💥 Erreur vérification données récentes : {e}")
            return False


async def get_last_timestamp(pool, symbol: str):
    table_name = "ohlcv_" + symbol.lower().replace("_", "__")
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = $1
            )
            """,
            table_name
        )
        if not exists:
            return None
        last_ts = await conn.fetchval(
            f"""
            SELECT MAX(timestamp) FROM {table_name}
            """
        )
        return last_ts


async def handle_live_symbol(symbol: str, pool, real_run: bool, dry_run: bool):
    try:
        log(f"[{symbol}] 📈 Chargement OHLCV pour {INTERVAL}")

        # Vérification existence et fraîcheur des données
        if not await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            log(f"[{symbol}] Ignoré : pas de données récentes")
            return

        if INTERVAL == "1s":
            end_ts = datetime.now(timezone.utc)
            start_ts = end_ts - timedelta(seconds=60)  # dernière minute de données 1s
            df = await fetch_ohlcv_1s(symbol, start_ts, end_ts)
        else:
            data = get_ohlcv(symbol, INTERVAL)
            if not data:
                log(f"[{symbol}] ❌ Données OHLCV vides")
                return
            df = get_ohlcv_df(symbol, INTERVAL)

        if df.empty:
            log(f"[{symbol}] ❌ DataFrame OHLCV vide après conversion")
            return
        if len(df) < 2:
            log(f"[{symbol}] ⚠️ Pas assez de données (moins de 2 lignes) pour calculer le signal")
            return

        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
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

async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False):
    if auto_select:
        log("🔍 Mode auto-select actif — sélection des symboles les plus volatils")
        try:
            symbols = fetch_top_n_perp(n=len(symbols))
            log(f"✅ Symboles sélectionnés automatiquement : {symbols}")
        except Exception as e:
            log(f"💥 Erreur sélection symboles auto: {e}")
            return

    active_symbols = []
    ignored_symbols = []

    for symbol in symbols:
        if await check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
            active_symbols.append(symbol)
            await handle_live_symbol(symbol, pool, real_run, dry_run)
        else:
            ignored_symbols.append(symbol)

    # Résumé après traitement avec date dernière donnée pour symboles ignorés
    if active_symbols:
        log(f"✅ Symboles actifs ({len(active_symbols)}) : {active_symbols}")
    if ignored_symbols:
        ignored_details = []
        for sym in ignored_symbols:
            last_ts = await get_last_timestamp(pool, sym)
            if last_ts is None:
                ignored_details.append(f"{sym} (table absente)")
            else:
                ignored_details.append(f"{sym} (dernière donnée : {last_ts.isoformat()})")
        log(f"⛔ Symboles ignorés ({len(ignored_symbols)}) : {ignored_details}")
    if not active_symbols:
        log("⚠️ Aucun symbole actif pour cette itération.")

async def watch_symbols_file(filepath: str = "symbol.lst", pool=None, real_run: bool = False, dry_run: bool = False):
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                symbols = load_symbols_from_file(filepath)
                log(f"🔁 symbol.lst rechargé : {symbols}")
                last_modified = current_modified

            await main_loop(symbols, pool, real_run=real_run, dry_run=dry_run)
        except KeyboardInterrupt:
            log("🛑 Arrêt manuel demandé")
            break
        except Exception as e:
            log(f"💥 Erreur dans le watcher : {e}")
            traceback.print_exc()

        await asyncio.sleep(1)

async def async_main(args):
    pool = await asyncpg.create_pool(dsn=os.environ.get("PG_DSN"))

    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def shutdown():
        log("🛑 Arrêt manuel demandé (Ctrl+C)")
        stop_event.set()

    # Capturer SIGINT (Ctrl+C) proprement
    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

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
            # Lancer la boucle avec arrêt possible
            task = asyncio.create_task(main_loop(symbols, pool, real_run=args.real_run, dry_run=args.dry_run, auto_select=args.auto_select))
            await asyncio.wait([task, stop_event.wait()], return_when=asyncio.FIRST_COMPLETED)
        else:
            # watcher avec arrêt possible
            task = asyncio.create_task(watch_symbols_file(pool=pool, real_run=args.real_run, dry_run=args.dry_run))
            await asyncio.wait([task, stop_event.wait()], return_when=asyncio.FIRST_COMPLETED)

    # Fermer proprement la connexion
    await pool.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breakout MACD RSI bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Liste des symboles (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Activer l'exécution réelle")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation sans exécuter de trade")
    parser.add_argument("--backtest", type=str, help="Exécuter un backtest (ex: 1h, 1d, 1w)")
    parser.add_argument("--auto-select", action="store_true", help="Sélection automatique des symboles les plus volatils")

    args = parser.parse_args()

    asyncio.run(async_main(args))
