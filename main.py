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
from live.live_engine import handle_live_symbol
from utils.i18n import t

config = load_config()

# ✅ RÉCUPÉRATION SÉCURISÉE DES SYMBOLES AUTO
def get_auto_symbols():
    """Récupère les symboles automatiques avec gestion d'erreur"""
    try:
        auto_symbols_result = fetch_top_n_volatility_volume(
            n=config.strategy.auto_select_top_n
        )
        symbols = auto_symbols_result if auto_symbols_result is not None else []
        log(f"Auto symbols récupérés avec succès: {symbols}", level="DEBUG")
        return symbols
    except Exception as e:
        log(f"Erreur lors de la récupération des auto_symbols: {e}", level="ERROR")
        return []


def calculate_final_symbols():
    """Calcule la liste finale des symboles en appliquant include/exclude"""
    auto_symbols = get_auto_symbols()
    include_symbols = getattr(config.strategy, 'include', []) or []
    exclude_symbols = getattr(config.strategy, 'exclude', []) or []
    
    log(f"Auto symbols: {auto_symbols}", level="DEBUG")
    log(f"Include symbols: {include_symbols}", level="DEBUG")
    log(f"Exclude symbols: {exclude_symbols}", level="DEBUG")
    
    # Fusion avec include (ajoute les symboles forcés)
    all_symbols = list(set(auto_symbols + include_symbols))
    
    # Application du filtre exclude (retire les symboles interdits)
    final_symbols = [s for s in all_symbols if s not in exclude_symbols]
    
    log(f"Final symbols: {final_symbols}", level="DEBUG")
    return final_symbols

# ✅ INITIALISATION PROPRE DES SYMBOLES
symbols_container = {'list': calculate_final_symbols()}

# Lance le thread de mise à jour périodique des symboles (thread daemon)
update_symbols_periodically(symbols_container)

async def main_loop(symbols: list, pool, real_run: bool, dry_run: bool, auto_select=False, symbols_container=None, args=None):
    """Version optimisée de la boucle principale classique"""
    last_symbols_check = 0
    last_api_calls = {}  # timestamp du dernier appel par symbole
    
    while True:
        current_time = time.time()
        
        if auto_select and symbols_container:
            symbols = symbols_container.get('list', [])
            log(f"Symbols list updated in main_loop: {symbols}", level="DEBUG")

        # ✅ UTILISATION DIRECTE DE LA CONFIG au lieu de variables globales
        if current_time - last_symbols_check >= config.performance.symbols_check_interval:
            active_symbols = []
            ignored_symbols = []
            
            for symbol in symbols:
                if await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
                    active_symbols.append(symbol)
                else:
                    ignored_symbols.append(symbol)
            
            last_symbols_check = current_time
            
            if active_symbols:
                log(f"Active symbols ({len(active_symbols)}): {active_symbols}", level="DEBUG")
            
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
                    log(f"Ignored symbols ({len(ignored_details)}): {ignored_details}", level="DEBUG")
        
        # Traiter les symboles actifs avec throttling
        for symbol in active_symbols:
            log(f"[MAIN LOOP] Processing symbol: {symbol}", level="DEBUG")
            # ✅ UTILISATION DIRECTE DE LA CONFIG
            if symbol in last_api_calls:
                time_since_last = current_time - last_api_calls[symbol]
                if time_since_last < config.performance.api_call_interval:
                    continue  # Skip ce symbole pour cette itération
            
            try:
                await handle_live_symbol(symbol, pool, real_run, dry_run, args=args)
                last_api_calls[symbol] = current_time
            except Exception as e:
                log(f"[ERROR] Erreur lors du traitement de {symbol}: {e}", level="ERROR")
        
        if not active_symbols:
            log(f"No active symbols for this iteration", level="DEBUG")

        # ✅ CALCUL DYNAMIQUE DE L'ATTENTE basé sur la config
        sleep_time = max(1, config.performance.api_call_interval // len(symbols) if symbols else 1)
        await asyncio.sleep(sleep_time)


async def get_trailing_stop_info(symbol, side, entry_price, mark_price, amount=1.0):
    """
    ✅ VERSION SIMPLIFIÉE: Focus sur fermeture des positions en perte critique
    """
    try:
        # Calcul du PnL actuel
        if side == "long":
            pnl_pct = ((mark_price - entry_price) / entry_price) * 100
        else:  # short
            pnl_pct = ((entry_price - mark_price) / entry_price) * 100
        
        log(f"[STOP LOSS CHECK] {symbol}: PnL={pnl_pct:.2f}%", level="INFO")
        
        # ✅ FERMETURE IMMÉDIATE si PnL ≤ -2%
        if pnl_pct <= -2.0:
            log(f"🚨 STOP LOSS TRIGGERED: {symbol} PnL={pnl_pct:.2f}% ≤ -2.0%", level="WARNING")
            
            try:
                # Import des fonctions de fermeture
                from execute.close_position_percent import close_position_percent
                
                # Fermer la position immédiatement
                result = await close_position_percent(symbol, 100.0)
                
                log(f"✅ {symbol} Position closed due to stop loss. Result: {result}", level="WARNING")
                
                return "CLOSED 🔴"
                
            except Exception as close_error:
                log(f"❌ {symbol} Error closing position: {close_error}", level="ERROR")
                return f"FAILED 🔴"
        
        # ✅ Tentative de récupération du trailing stop (sans erreur critique)
        try:
            from live.live_engine import get_position_trailing_stop
            trailing_stop = await get_position_trailing_stop(symbol, side, entry_price, mark_price, amount)
            
            if trailing_stop is not None:
                # Position avec trailing stop actif
                will_trigger_soon = pnl_pct <= (trailing_stop + 0.1)
                status = "⚠️" if will_trigger_soon else "✅"
                return f"{trailing_stop:+.1f}% {status}"
            else:
                # Pas de trailing stop actif
                if pnl_pct > 0:
                    return f"+{pnl_pct:.1f}% 🟢"  # En profit
                else:
                    return f"-2.0% ⏸️"  # Stop loss fixe
                    
        except Exception as trailing_error:
            log(f"Warning: Could not get trailing stop for {symbol}: {trailing_error}", level="DEBUG")
            
            # Fallback simple sans trailing stop
            if pnl_pct > 0:
                return f"+{pnl_pct:.1f}% 🟢"
            else:
                return f"-2.0% ⏸️"
                
    except Exception as e:
        log(f"Error in get_trailing_stop_info for {symbol}: {e}", level="ERROR")
        return "ERROR"

async def force_close_critical_positions():
    """
    ✅ FONCTION D'URGENCE: Ferme toutes les positions avec PnL ≤ -2%
    """
    try:
        from utils.position_utils import get_real_positions
        from execute.close_position_percent import close_position_percent
        
        positions = await get_real_positions()
        closed_count = 0
        
        for pos in positions:
            symbol = pos['symbol']
            pnl_pct = pos['pnl_pct']
            
            if pnl_pct <= -2.0:
                try:
                    log(f"🚨 FORCE CLOSING: {symbol} with PnL {pnl_pct:.2f}%", level="WARNING")
                    result = await close_position_percent(symbol, 100.0)
                    log(f"✅ {symbol} Force closed successfully", level="WARNING")
                    closed_count += 1
                except Exception as e:
                    log(f"❌ {symbol} Force close failed: {e}", level="ERROR")
        
        if closed_count > 0:
            log(f"🎯 Force closed {closed_count} critical positions", level="WARNING")
        
        return closed_count
        
    except Exception as e:
        log(f"Error in force_close_critical_positions: {e}", level="ERROR")
        return 0

async def refresh_dashboard_with_counts(active_symbols, ignored_symbols):
    """✅ CORRECTION: Dashboard qui déclenche aussi les fermetures de positions"""
    import os
    from datetime import datetime
    from tabulate import tabulate
    
    try:
        os.system("clear")
        print("=" * 120)
        print(f"🚀 VERSION 24 FINALE - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"Active symbols: {len(active_symbols)}, Ignored symbols: {len(ignored_symbols)}")
        
        if active_symbols:
            print(f"📈 Active: {', '.join(active_symbols[:5])}" + ("..." if len(active_symbols) > 5 else ""))
        
        from utils.position_utils import get_real_positions
        positions = await get_real_positions()
        
        if positions:
            positions_data = []
            total_pnl = 0.0
            positions_to_close = []  # ✅ NOUVEAU: Liste des positions à fermer
            
            for pos in positions:
                side_icon = "🟢" if pos["side"] == "long" else "🔴"
                
                if pos["pnl_pct"] > 0:
                    pnl_icon = "📈"
                elif pos["pnl_pct"] < 0:
                    pnl_icon = "📉"
                else:
                    pnl_icon = "➡️"
                    
                simple_symbol = pos['symbol'].split('_')[0]
                
                # ✅ CORRECTION: Passer le montant pour hash stable
                trailing_stop_info = await get_trailing_stop_info(
                    pos['symbol'], 
                    pos['side'], 
                    pos['entry_price'], 
                    pos['mark_price'],
                    pos.get('amount', 1.0)  # Passer le montant réel
                )
                
                # ✅ DÉTECTION: Position qui devrait être fermée
                if pos['pnl_pct'] <= -2.0:
                    positions_to_close.append(pos['symbol'])
                    pnl_icon = "🚨"  # Alerte critique
                
                positions_data.append([
                    f"{side_icon} {simple_symbol}",
                    pos["side"].upper(),
                    f"{pos['entry_price']:.6f}",
                    f"{pos['mark_price']:.6f}",
                    f"{pnl_icon} {pos['pnl_pct']:+.2f}%",
                    f"${pos['pnl_usd']:+.2f}",
                    f"{pos['amount']:.6f}",
                    trailing_stop_info
                ])
                
                total_pnl += pos["pnl_usd"]
            
            print(f"💰 PnL Total: ${total_pnl:+.2f}")
            
            # ✅ ALERTE: Afficher les positions critiques
            if positions_to_close:
                print(f"🚨 CRITICAL: {len(positions_to_close)} positions should be closed: {positions_to_close}")
            
            print("=" * 120)
            
            print(tabulate(
                positions_data,
                headers=["Symbol", "S", "Entry", "Mark", "PnL%", "PnL$", "Amount", "Trailing Stop"],
                tablefmt="grid"
            ))
            print("=" * 120)
            print(f"Legend: ✅ = Trailing stop active | ⏸️ = Fixed stop loss ({config.strategy.default_strategy}) | "
                  f"Trigger: {config.trading.trailing_stop_trigger}% | Min PnL: {config.trading.min_pnl_for_trailing}%")
            print("=" * 120)
        else:
            print("💰 PnL Total: $+0.00")
            print("=" * 120)
            print("No open positions yet.")
            print("=" * 120)
            
    except Exception as e:
        log(f"Erreur dans refresh_dashboard_with_counts: {e}", level="ERROR")
        import traceback
        traceback.print_exc()

async def async_main(args):
    # ✅ UTILISATION DIRECTE DE LA CONFIG
    pool = await asyncpg.create_pool(
        dsn=config.pg_dsn or os.environ.get("PG_DSN"),
        min_size=config.database.pool_min_size,
        max_size=config.database.pool_max_size
    )

    from utils.scan_all_symbols import scan_all_symbols

    # Choix des symbols à scanner
    if args.auto_select:
        initial_symbols = get_auto_symbols()
    elif args.symbols:
        initial_symbols = args.symbols.split(",")
    else:
        initial_symbols = load_symbols_from_file()

    log(f"Initial scan of symbols before main loop: {initial_symbols}", level="DEBUG")
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
            # Mode backtest
            log("Mode backtest activé", level="DEBUG")
            if args.symbols:
                symbols = args.symbols.split(",")
            else:
                symbols = load_symbols_from_file()

            if not symbols:
                log("Liste de symboles vide, backtest annulé", level="ERROR")
                return

            if isinstance(args.backtest, tuple):
                start_dt, end_dt = args.backtest
                for symbol in symbols:
                    await run_backtest_async(symbol, (start_dt, end_dt), config.pg_dsn or os.environ.get("PG_DSN"), args.strategie)
            else:
                for symbol in symbols:
                    await run_backtest_async(symbol, args.backtest, config.pg_dsn or os.environ.get("PG_DSN"), args.strategie)

        else:
            # Mode live
            from live.live_engine import handle_live_symbol

            async def dashboard_loop():
                """Boucle pour le mode textdashboard avec positions ouvertes"""
                last_symbols_check = 0
                last_api_calls = {}
                active_symbols = []
                ignored_symbols = []
                
                while not stop_event.is_set():
                    current_time = time.time()
                    
                    # Détermination des symboles à traiter
                    if args.auto_select:
                        current_symbols = symbols_container.get('list', [])
                    elif args.symbols:
                        current_symbols = args.symbols.split(",")
                    else:
                        current_symbols = []
                    
                    # ✅ DEBUG LOG AJOUTÉ
                    log(f"[DEBUG] Current symbols to check: {current_symbols}", level="INFO")
                    
                    # ✅ UTILISATION DIRECTE DE LA CONFIG
                    if current_time - last_symbols_check >= config.performance.symbols_check_interval:
                        active_symbols = []
                        ignored_symbols = []
                        
                        for symbol in current_symbols:
                            if await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds):
                                active_symbols.append(symbol)
                            else:
                                ignored_symbols.append(symbol)
                        
                        # ✅ DEBUG LOGS DÉPLACÉS APRÈS LA BOUCLE
                        log(f"[DEBUG] Active symbols list: {active_symbols}", level="INFO")
                        log(f"[DEBUG] Ignored symbols list: {ignored_symbols}", level="INFO")
                        
                        last_symbols_check = current_time
                        
                        if active_symbols:
                            log(f"Active symbols ({len(active_symbols)}): {active_symbols}", level="DEBUG")
                        
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
                                log(f"Ignored symbols ({len(ignored_details)}): {ignored_details}", level="DEBUG")
                    
                    await refresh_dashboard_with_counts(active_symbols, ignored_symbols)
                    
                    # Traitement des symboles actifs avec throttling
                    for symbol in active_symbols:
                        log(f"[MAIN LOOP] Processing symbol: {symbol}", level="DEBUG")
                        # ✅ UTILISATION DIRECTE DE LA CONFIG
                        if symbol in last_api_calls:
                            time_since_last = current_time - last_api_calls[symbol]
                            if time_since_last < config.performance.api_call_interval:
                                continue  # Skip ce symbole pour cette itération
                        
                        try:
                            await handle_live_symbol(symbol, pool, real_run, dry_run, args)
                            last_api_calls[symbol] = current_time
                        except Exception as e:
                            log(f"[ERROR] Erreur lors du traitement de {symbol}: {e}", level="ERROR")
                    
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
        log(f"Connection pool closed, program terminated", level="ERROR")

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
    parser.add_argument("--api-interval", type=int, default=None, help="API call interval in seconds")
    parser.add_argument("--dashboard-interval", type=int, default=None, help="Dashboard refresh interval in seconds")
    parser.add_argument("--symbols-check-interval", type=int, default=None, help="Symbols status check interval in seconds")
    args = parser.parse_args()

    # ✅ RECHARGEMENT DE CONFIG SI FICHIER DIFFÉRENT SPÉCIFIÉ
    if args.config != "config/settings.yaml":
        config = load_config(args.config)

    # ✅ OVERRIDE PROPRE DES VALEURS DE CONFIG
    if args.api_interval:
        config.performance.api_call_interval = args.api_interval
    if args.dashboard_interval:
        config.performance.dashboard_refresh_interval = args.dashboard_interval
    if args.symbols_check_interval:
        config.performance.symbols_check_interval = args.symbols_check_interval

    if args.strategie is None:
        args.strategie = config.strategy.default_strategy

    try:
        strategy_imports = {
            "Trix": "signals.trix_only_signal",
            "Combo": "signals.macd_rsi_bo_trix", 
            "RangeSoft": "signals.range_soft_signal",
            "ThreeOutOfFour": "signals.three_out_of_four_conditions",
            "TwoOutOfFourScalp": "signals.two_out_of_four_scalp",
            "DynamicThreeTwo": "signals.dynamic_three_two_selector"
        }
        
        if args.strategie in strategy_imports:
            module = __import__(strategy_imports[args.strategie], fromlist=['get_combined_signal'])
            args.get_combined_signal = module.get_combined_signal
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




