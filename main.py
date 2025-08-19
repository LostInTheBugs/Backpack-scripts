import argparse
import os
import traceback
import asyncio
from datetime import datetime, timezone
import asyncpg
import signal
import sys
from tabulate import tabulate
import time

from utils.logger import log
from utils.public import check_table_and_fresh_data, get_last_timestamp, load_symbols_from_file
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from live.live_engine import handle_live_symbol
from backtest.backtest_engine import run_backtest_async, parse_backtest
from config.settings import load_config
from utils.update_symbols_periodically import update_symbols_periodically
from utils.watch_symbols_file import watch_symbols_file
from utils.i18n import t, set_locale, get_available_locales

# Charge la config au démarrage
config = load_config()

public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

# Configuration des intervalles (en secondes) - avec valeurs par défaut
API_CALL_INTERVAL = 5  # Minimum entre appels API par symbole
DASHBOARD_REFRESH_INTERVAL = 2  # Rafraîchissement du dashboard
SYMBOLS_CHECK_INTERVAL = 30  # Vérification du statut des symboles

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

class OptimizedDashboard:
    def __init__(self, symbols_container, pool, real_run, dry_run, args):
        self.symbols_container = symbols_container
        self.pool = pool
        self.real_run = real_run
        self.dry_run = dry_run
        self.args = args
        
        # Cache des données
        self.trade_events = []
        self.open_positions = {}
        self.active_symbols = []
        self.ignored_symbols = []
        
        # Timestamps pour contrôler les intervalles
        self.last_api_call = {}  # par symbole
        self.last_symbols_check = 0
        
        # Verrous pour éviter les appels concurrents
        self.processing_symbols = set()
        
        # Limite de concurrence pour éviter trop de connexions
        self.max_concurrent_symbols = min(5, config.database.pool_max_size - 2)
        self.symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)
        
    async def check_symbols_status(self):
        """Vérifie le statut des symboles (actifs/ignorés) - moins fréquent"""
        current_time = time.time()
        if current_time - self.last_symbols_check < SYMBOLS_CHECK_INTERVAL:
            return
            
        self.last_symbols_check = current_time
        symbols = self.symbols_container.get("list", [])
        
        new_active = []
        new_ignored = []
        
        for symbol in symbols:
            try:
                if await check_table_and_fresh_data(self.pool, symbol, max_age_seconds=config.database.max_age_seconds):
                    new_active.append(symbol)
                else:
                    new_ignored.append(symbol)
            except Exception as e:
                new_ignored.append(symbol)
                log(f"[ERROR] check_table_and_fresh_data {symbol}: {e}", level="ERROR")
        
        self.active_symbols = new_active
        self.ignored_symbols = new_ignored
        
        log(f"Symbols status updated: {len(new_active)} active, {len(new_ignored)} ignored", level="DEBUG")

    async def process_symbol_with_throttling(self, symbol):
        """Traite un symbole avec limitation du taux d'appels API et gestion des connexions"""
        current_time = time.time()
        
        # Vérifier si on doit attendre avant le prochain appel
        if symbol in self.last_api_call:
            time_since_last = current_time - self.last_api_call[symbol]
            if time_since_last < API_CALL_INTERVAL:
                return  # Skip cet appel
        
        # Éviter les appels concurrents pour le même symbole
        if symbol in self.processing_symbols:
            return
        
        # Limiter le nombre de symboles traités simultanément
        async with self.symbol_semaphore:
            self.processing_symbols.add(symbol)
            
            try:
                # Marquer l'heure de l'appel
                self.last_api_call[symbol] = current_time
                
                # Appel à l'API avec le pool existant
                result = await self.handle_live_symbol_with_pool(symbol)
                
                if result:
                    action = result.get("signal", "N/A")
                    price = result.get("price", 0.0)
                    pnl = result.get("pnl", 0.0)
                    amount = result.get("amount", 0.0)
                    duration = result.get("duration", "0s")
                    trailing_stop = result.get("trailing_stop", 0.0)
                    
                    # Ajouter l'événement de trade si un signal est présent
                    if action in ["BUY", "SELL"]:
                        self.trade_events.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "action": action,
                            "price": price
                        })
                        # Garder seulement les 20 derniers événements
                        if len(self.trade_events) > 20:
                            self.trade_events = self.trade_events[-20:]
                    
                    # Mettre à jour les positions ouvertes
                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "pnl": pnl,
                        "amount": amount,
                        "duration": duration,
                        "trailing_stop": trailing_stop
                    }
                else:
                    # Supprimer la position si fermée
                    if symbol in self.open_positions:
                        del self.open_positions[symbol]
                        
            except Exception as e:
                log(f"[ERROR] Impossible de traiter {symbol}: {e}", level="ERROR")
                # En cas d'erreur de connexion, attendre plus longtemps
                if "too many clients" in str(e).lower():
                    log(f"[WARNING] Too many connections, increasing interval for {symbol}", level="WARNING")
                    self.last_api_call[symbol] = current_time + API_CALL_INTERVAL * 2
            finally:
                self.processing_symbols.discard(symbol)

    async def handle_live_symbol_with_pool(self, symbol):
        """Version modifiée de handle_live_symbol qui utilise le pool existant"""
        try:
            # Au lieu d'appeler handle_live_symbol qui peut créer de nouvelles connexions,
            # on utilise directement le pool existant
            result = await handle_live_symbol(symbol, self.pool, self.real_run, self.dry_run, args=self.args)
            return result
        except Exception as e:
            # Si on a une erreur de connexion, on peut essayer de récupérer
            if "too many clients" in str(e).lower():
                log(f"[ERROR] Connection pool exhausted for {symbol}, will retry later", level="ERROR")
                await asyncio.sleep(API_CALL_INTERVAL)
            raise

    async def symbol_processor(self):
        """Processeur principal pour tous les symboles avec throttling et gestion des connexions"""
        while True:
            try:
                # Vérifier le statut des symboles périodiquement
                await self.check_symbols_status()
                
                # Limiter le nombre de symboles actifs si trop nombreux
                active_symbols = self.active_symbols
                if len(active_symbols) > self.max_concurrent_symbols:
                    log(f"Too many active symbols ({len(active_symbols)}), processing only first {self.max_concurrent_symbols}", level="WARNING")
                    active_symbols = active_symbols[:self.max_concurrent_symbols]
                
                # Traiter les symboles actifs avec throttling et limitation de concurrence
                tasks = []
                for i, symbol in enumerate(active_symbols):
                    # Étaler les appels dans le temps pour éviter les pics
                    delay = (i * API_CALL_INTERVAL) / len(active_symbols) if active_symbols else 0
                    task = asyncio.create_task(self._process_symbol_delayed(symbol, delay))
                    tasks.append(task)
                
                # Attendre que toutes les tâches se terminent (ou timeout)
                if tasks:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*tasks, return_exceptions=True), 
                            timeout=API_CALL_INTERVAL * 2
                        )
                    except asyncio.TimeoutError:
                        log("Some API calls timed out, continuing...", level="WARNING")
                
                # Attendre avant la prochaine itération
                await asyncio.sleep(max(1, API_CALL_INTERVAL // 2))
                
            except Exception as e:
                log(f"[ERROR] Erreur dans symbol_processor: {e}", level="ERROR")
                await asyncio.sleep(5)  # Attendre plus longtemps en cas d'erreur

    async def _process_symbol_delayed(self, symbol, delay):
        """Traite un symbole avec un délai pour étaler les appels"""
        if delay > 0:
            await asyncio.sleep(delay)
        await self.process_symbol_with_throttling(symbol)

    async def render_dashboard(self):
        """Rendu du dashboard avec intervalle contrôlé"""
        while True:
            try:
                await asyncio.sleep(DASHBOARD_REFRESH_INTERVAL)
                
                # Clear terminal
                os.system("clear")
                
                # Afficher les informations de configuration
                print(f"=== CONFIGURATION ===")
                print(f"API Call Interval: {API_CALL_INTERVAL}s")
                print(f"Dashboard Refresh: {DASHBOARD_REFRESH_INTERVAL}s")
                print(f"Symbols Check: {SYMBOLS_CHECK_INTERVAL}s")
                print()
                
                # === SYMBOLS ===
                print("=== SYMBOLS ===")
                print(tabulate([
                    ["Active", f"{len(self.active_symbols)} symbols: {', '.join(self.active_symbols[:10])}{' ...' if len(self.active_symbols) > 10 else ''}"],
                    ["Ignored", f"{len(self.ignored_symbols)} symbols: {', '.join(self.ignored_symbols[:10])}{' ...' if len(self.ignored_symbols) > 10 else ''}"]
                ], headers=["Status", "Symbols"], tablefmt="fancy_grid"))
                
                # === API CALL STATUS ===
                print("\n=== API CALL STATUS ===")
                current_time = time.time()
                api_status = []
                for symbol in self.active_symbols[:5]:  # Montrer seulement les 5 premiers
                    last_call = self.last_api_call.get(symbol, 0)
                    if last_call > 0:
                        seconds_ago = int(current_time - last_call)
                        status = "Processing" if symbol in self.processing_symbols else f"Last call: {seconds_ago}s ago"
                        api_status.append([symbol, status])
                    else:
                        api_status.append([symbol, "No calls yet"])
                
                if api_status:
                    print(tabulate(api_status, headers=["Symbol", "API Status"], tablefmt="fancy_grid"))
                else:
                    print("No API calls tracked yet.")
                
                # === TRADE EVENTS ===
                print("\n=== TRADE EVENTS ===")
                if self.trade_events:
                    print(tabulate(self.trade_events[-10:], headers="keys", tablefmt="fancy_grid"))
                else:
                    print("No trades yet.")
                
                # === OPEN POSITIONS ===
                print("\n=== OPEN POSITIONS ===")
                if self.open_positions:
                    positions_data = []
                    for p in self.open_positions.values():
                        positions_data.append([
                            p["symbol"], 
                            f'{p["pnl"]:.2f}%', 
                            p["amount"], 
                            p["duration"], 
                            f'{p["trailing_stop"]}%'
                        ])
                    print(tabulate(
                        positions_data,
                        headers=["Symbol", "PnL", "Amount", "Duration", "Trailing Stop"], 
                        tablefmt="fancy_grid"
                    ))
                else:
                    print("No open positions yet.")
                
                # Statistiques
                print(f"\n=== STATS ===")
                print(f"Total API calls tracked: {len(self.last_api_call)}")
                print(f"Symbols currently processing: {len(self.processing_symbols)}")
                print(f"Max concurrent symbols: {self.max_concurrent_symbols}")
                print(f"Pool size: {config.database.pool_min_size}-{config.database.pool_max_size}")
                print(f"Last symbols check: {int(current_time - self.last_symbols_check)}s ago")
                
            except Exception as e:
                log(f"[ERROR] Erreur dans render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)


async def main_loop_textdashboard(symbols: list, pool, real_run: bool, dry_run: bool, symbols_container=None):
    """
    Boucle principale optimisée pour le dashboard texte en live.
    """
    if symbols_container is None:
        symbols_container = {"list": symbols}
    
    dashboard = OptimizedDashboard(symbols_container, pool, real_run, dry_run, args)
    
    # Créer les tâches
    processor_task = asyncio.create_task(dashboard.symbol_processor())
    render_task = asyncio.create_task(dashboard.render_dashboard())
    
    # Attendre que les deux tâches se terminent
    await asyncio.gather(processor_task, render_task)


async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None):
    """Version optimisée de la boucle principale classique"""
    last_symbols_check = 0
    last_api_calls = {}  # timestamp du dernier appel par symbole
    
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

    from utils.scan_all_symbols import scan_all_symbols  # Ajuste chemin si besoin

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

    try:
        if args.backtest:
            # -------------------------
            # Mode backtest
            # -------------------------
            log(" Mode backtest activé", level="DEBUG")
            log(f" Backtest demandé avec valeur: {args.backtest}", level="DEBUG")
            if args.symbols:
                symbols = args.symbols.split(",")
                log(f" Symboles passés en argument: {symbols}", level="DEBUG")
            else:
                symbols = load_symbols_from_file()
                log(f" Symboles chargés depuis fichier: {symbols}", level="DEBUG")

            if not symbols:
                log(" Liste de symboles vide, backtest annulé", level="ERROR")
                return

            if isinstance(args.backtest, tuple):
                start_dt, end_dt = args.backtest
                for symbol in symbols:
                    log(f" [{symbol}] Starting backtest from {start_dt.date()} to {end_dt.date()} with {args.strategie} strategy", level="DEBUG")
                    await run_backtest_async(symbol, (start_dt, end_dt), pg_dsn, args.strategie)
            else:
                for symbol in symbols:
                    log(f" [{symbol}] Starting {args.backtest}h backtest with {args.strategie} strategy", level="DEBUG")
                    await run_backtest_async(symbol, args.backtest, pg_dsn, args.strategie)
        else:
            # -------------------------
            # Mode live
            # -------------------------
            log(" Mode live (pas de backtest)", level="DEBUG")

            # Choix du mode textdashboard ou mode classique
            if getattr(args, "mode", None) == "textdashboard":
                # Mode textdashboard optimisé
                if args.auto_select:
                    task = asyncio.create_task(
                        main_loop_textdashboard(
                            [], pool, real_run=args.real_run, dry_run=args.dry_run, symbols_container=symbols_container
                        )
                    )
                elif args.symbols:
                    symbols = args.symbols.split(",")
                    task = asyncio.create_task(
                        main_loop_textdashboard(
                            symbols, pool, real_run=args.real_run, dry_run=args.dry_run
                        )
                    )
                else:
                    task = asyncio.create_task(
                        watch_symbols_file(pool=pool, real_run=args.real_run, dry_run=args.dry_run)
                    )
            else:
                # Mode classique optimisé
                if args.auto_select:
                    task = asyncio.create_task(
                        main_loop(
                            [], pool, real_run=args.real_run, dry_run=args.dry_run, auto_select=True, symbols_container=symbols_container
                        )
                    )
                elif args.symbols:
                    symbols = args.symbols.split(",")
                    task = asyncio.create_task(
                        main_loop(symbols, pool, real_run=args.real_run, dry_run=args.dry_run)
                    )
                else:
                    task = asyncio.create_task(
                        watch_symbols_file(pool=pool, real_run=args.real_run, dry_run=args.dry_run)
                    )

            # Attente Ctrl+C ou fin de tâche
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
    parser.add_argument("--dry-run", action="store_true", help="Simulation mode without executing trades")
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