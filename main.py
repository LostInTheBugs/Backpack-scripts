#main.py
import argparse
import os
import traceback
import asyncio
from datetime import datetime, timezone
import asyncpg
import signal
import sys
import time

from utils.logger import log
from utils.public import check_table_and_fresh_data, get_last_timestamp, load_symbols_from_file
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from backtest.backtest_engine import run_backtest_async, parse_backtest
from config.settings import load_config
from utils.update_symbols_periodically import update_symbols_periodically
from utils.watch_symbols_file import watch_symbols_file
from utils.i18n import t, set_locale, get_available_locales
from live.live_engine import get_handle_live_symbol
from dashboard.textdashboard import refresh_dashboard

# Charge la config au démarrage
config = load_config()

public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

# Essayer de charger depuis la config si disponible
try:
    if hasattr(config, 'performance') and hasattr(config.performance, 'api_call_interval'):
        API_CALL_INTERVAL = config.performance.api_call_interval
    if hasattr(config, 'performance') and hasattr(config.performance, 'dashboard_refresh_interval'):
        DASHBOARD_REFRESH_INTERVAL = config.performance.dashboard_refresh_interval
    if hasattr(config, 'performance') and hasattr(config.performance, 'symbols_check_interval'):
        SYMBOLS_CHECK_INTERVAL = config.performance.symbols_check_interval
except AttributeError:
    # Utiliser les valeurs par défaut si la config n'a pas ces champs
    pass

# Sécurise auto_symbols avec gestion d'erreur améliorée
try:
    auto_symbols_result = fetch_top_n_volatility_volume(n=getattr(config.strategy, "auto_select_top_n", 10))
    auto_symbols = auto_symbols_result if auto_symbols_result is not None else []
    log(f"Auto symbols récupérés avec succès: {auto_symbols}", level="DEBUG")
except Exception as e:
    log(f"Erreur lors de la récupération des auto_symbols: {e}", level="ERROR")
    auto_symbols = []

# Vérifier si include et exclude existent dans la config
include_symbols = getattr(config.strategy, 'include', []) or []
exclude_symbols = getattr(config.strategy, 'exclude', []) or []

log(f"Auto symbols: {auto_symbols}", level="DEBUG")
log(f" Include symbols: {include_symbols}", level="DEBUG")
log(f" Exclude symbols: {exclude_symbols}", level="DEBUG")

# On fusionne avec include (ajoute les symboles forcés)
all_symbols = list(set(auto_symbols + include_symbols))

# On applique le filtre exclude (retire les symboles interdits)
final_symbols = [s for s in all_symbols if s not in exclude_symbols]

log(f" Final symbols: {final_symbols}", level="DEBUG")

symbols_container = {'list': final_symbols}

# Lance le thread de mise à jour périodique des symboles (thread daemon)
update_symbols_periodically(symbols_container)


async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None, args=None):
    """Version optimisée de la boucle principale classique"""
    last_symbols_check = 0
    last_api_calls = {}  # timestamp du dernier appel par symbole
    
    # Lazy load handle_live_symbol to avoid circular import
    handle_live_symbol = None
    
    while True:
        current_time = time.time()
        
        if auto_select and symbols_container:
            symbols = symbols_container.get('list', [])
            log(f" Symbols list updated in main_loop: {symbols}")

        # Vérifier les symboles actifs moins fréquemment
        if current_time - last_symbols_check >= SYMBOLS_CHECK_INTERVAL:
            active_symbols = []
            ignored_symbols = []
            
            for symbol in symbols:
                if await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
                    active_symbols.append(symbol)
                else:
                    ignored_symbols.append(symbol)
            
            last_symbols_check = current_time
            
            if active_symbols:
                log(f" Active symbols ({len(active_symbols)}): {active_symbols}", level="INFO")
            
            if ignored_symbols:
                ignored_details = []
                for sym in ignored_symbols:
                    last_ts = await get_last_timestamp(pool, sym)
                    if last_ts is None:
                        ignored_details.append(f"{sym} (table missing)")
                    else:
                        now = datetime.now(timezone.utc)
                        delay = now - last_ts
                        seconds = int(delay.total_seconds())
                        human_delay = f"{seconds}s" if seconds < 120 else f"{seconds // 60}min"
                        ignored_details.append(f"{sym} (inactive for {human_delay})")
                
                if ignored_details:
                    log(f" Ignored symbols ({len(ignored_details)}): {ignored_details}", level="INFO")
        
        # Lazy load handle_live_symbol function
        if handle_live_symbol is None:
            handle_live_symbol = get_handle_live_symbol()
        
        # Traiter les symboles actifs avec throttling
        for symbol in active_symbols:
            # Vérifier si assez de temps s'est écoulé depuis le dernier appel
            if symbol in last_api_calls:
                time_since_last = current_time - last_api_calls[symbol]
                if time_since_last < API_CALL_INTERVAL:
                    continue  # Skip ce symbole pour cette itération
            
            try:
                await handle_live_symbol(symbol, pool, real_run, dry_run, args=args)
                last_api_calls[symbol] = current_time
            except Exception as e:
                log(f"[ERROR] Erreur lors du traitement de {symbol}: {e}", level="ERROR")
        
        if not active_symbols:
            log(f" No active symbols for this iteration", level="INFO")

        # Attendre avant la prochaine itération
        await asyncio.sleep(max(1, API_CALL_INTERVAL // len(symbols) if symbols else 1))


async def async_main(args):
    db_config = config.database
    pg_dsn = config.pg_dsn or os.environ.get("PG_DSN")

    pool = await asyncpg.create_pool(
        dsn=pg_dsn,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size
    )

    from utils.scan_all_symbols import scan_all_symbols

    # Choix des symbols à scanner
    if args.auto_select:
        initial_symbols = auto_symbols
    elif args.symbols:
        initial_symbols = args.symbols.split(",")
    else:
        initial_symbols = load_symbols_from_file()

    log(f" Initial scan of symbols before main loop: {initial_symbols}", level="DEBUG")
    await scan_all_symbols(pool, initial_symbols)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown():
        print("Manual stop requested (Ctrl+C)")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)

    real_run = getattr(args, "real_run", False)
    dry_run = getattr(args, "dry_run", True)

    try:
        if args.backtest:
            # -------------------------
            # Mode backtest
            # -------------------------
            log(" Mode backtest activé", level="DEBUG")
            if args.symbols:
                symbols = args.symbols.split(",")
            else:
                symbols = load_symbols_from_file()

            if not symbols:
                log(" Liste de symboles vide, backtest annulé", level="ERROR")
                return

            if isinstance(args.backtest, tuple):
                start_dt, end_dt = args.backtest
                for symbol in symbols:
                    await run_backtest_async(symbol, (start_dt, end_dt), pg_dsn, args.strategie)
            else:
                for symbol in symbols:
                    await run_backtest_async(symbol, args.backtest, pg_dsn, args.strategie)

        else:
            # -------------------------
            # Mode live
            # -------------------------
            from live.live_engine import get_handle_live_symbol

            async def dashboard_loop():
                """Boucle pour le mode textdashboard avec positions ouvertes"""
                while not stop_event.is_set():
                    await refresh_dashboard()

                    # Détermination des symboles à traiter
                    if args.auto_select:
                        current_symbols = symbols_container.get('list', [])
                    elif args.symbols:
                        current_symbols = args.symbols.split(",")
                    else:
                        current_symbols = []

                    handle_fn = get_handle_live_symbol()  # retourne la fonction handle_live_symbol
                    for symbol in current_symbols:
                        await handle_fn(symbol, pool, real_run, dry_run, args)

                    await asyncio.sleep(config.performance.dashboard_refresh_interval)

            # Choix du mode textdashboard ou mode classique
            if getattr(args, "mode", None) == "textdashboard":
                task = asyncio.create_task(dashboard_loop())
            else:
                # Mode classique optimisé
                if args.auto_select:
                    task = asyncio.create_task(
                        main_loop(
                            [],
                            pool,
                            real_run=real_run,
                            dry_run=dry_run,
                            auto_select=True,
                            symbols_container=symbols_container,
                            args=args
                        )
                    )
                elif args.symbols:
                    symbols = args.symbols.split(",")
                    task = asyncio.create_task(
                        main_loop(symbols, pool, real_run=real_run, dry_run=dry_run, args=args)
                    )
                else:
                    task = asyncio.create_task(
                        watch_symbols_file(pool=pool, real_run=real_run, dry_run=dry_run)
                    )

            stop_task = asyncio.create_task(stop_event.wait())
            await asyncio.wait([task, stop_task], return_when=asyncio.FIRST_COMPLETED)

    except Exception:
        traceback.print_exc()
    finally:
        await pool.close()
        log(f" Connection pool closed, program terminated", level="ERROR")




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot for Backpack Exchange")
    parser.add_argument("symbols", nargs="?", default="", help="Symbol list (ex: BTC_USDC_PERP,SOL_USDC_PERP)")
    parser.add_argument("--real-run", action="store_true", help="Enable real execution")
    parser.add_argument("--dry-run", action="store_true", help="Enable simulation mode without executing trades")
    parser.add_argument("--backtest", type=parse_backtest, help="Backtest duration (ex: 10m, 2h, 3d, 1w, or just a number = minutes)")
    parser.add_argument("--auto-select", action="store_true", help="Automatic selection of most volatile symbols")
    parser.add_argument('--strategie', type=str, default=None, help='Strategy name (Default, Trix, Combo, Auto, Range, RangeSoft, ThreeOutOfFour, TwoOutOfFourScalp and DynamicThreeTwo.)')
    parser.add_argument("--no-limit", action="store_true", help="Disable symbol count limit")
    parser.add_argument("--config", type=str, default="config/settings.yaml", help="Configuration file path")
    parser.add_argument("--mode", type=str, default="text", choices=["text", "textdashboard", "webdashboard"], help="Mode d'affichage")
    
    # Arguments pour les intervalles de performance
    parser.add_argument("--api-interval", type=int, default=None, help="API call interval in seconds (default: 5)")
    parser.add_argument("--dashboard-interval", type=int, default=None, help="Dashboard refresh interval in seconds (default: 2)")
    parser.add_argument("--symbols-check-interval", type=int, default=None, help="Symbols status check interval in seconds (default: 30)")
    
    args = parser.parse_args()

    # Override des intervalles si spécifiés en ligne de commande
    if args.api_interval:
        API_CALL_INTERVAL = args.api_interval
    if args.dashboard_interval:
        DASHBOARD_REFRESH_INTERVAL = args.dashboard_interval
    if args.symbols_check_interval:
        SYMBOLS_CHECK_INTERVAL = args.symbols_check_interval

    if args.config != "config/settings.yaml":
        config = load_config(args.config)

    if args.strategie is None:
        args.strategie = config.strategy.default_strategy

    try:
        if args.strategie == "Trix":
            from signals.trix_only_signal import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "Combo":
            from signals.macd_rsi_bo_trix import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "RangeSoft":
            from signals.range_soft_signal import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "ThreeOutOfFour":
            from signals.three_out_of_four_conditions import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "TwoOutOfFourScalp":
            from signals.two_out_of_four_scalp import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie == "DynamicThreeTwo":
            from signals.dynamic_three_two_selector import get_combined_signal
            args.get_combined_signal = get_combined_signal
        elif args.strategie in ["Auto", "AutoSoft", "Range"]:
            args.get_combined_signal = None
        else:
            from signals.macd_rsi_breakout import get_combined_signal
            args.get_combined_signal = get_combined_signal

        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("Manual stop requested via KeyboardInterrupt, clean shutdown...")
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)