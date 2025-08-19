# dashboard/textdashboard.py
import asyncio
import time
import os

from tabulate import tabulate
from datetime import datetime
from utils.public import check_table_and_fresh_data
from live.live_engine import get_handle_live_symbol
from utils.logger import log
from config.settings import load_config
from utils.position_utils import get_real_positions
from bpx.account import Account
from utils.get_market import get_market

config = load_config()
public_key = config.bpx_bot_public_key or os.getenv("bpx_bot_public_key")
secret_key = config.bpx_bot_secret_key or os.getenv("bpx_bot_secret_key")

account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)

# Configuration des intervalles (en secondes) - avec valeurs par défaut
API_CALL_INTERVAL = 5
DASHBOARD_REFRESH_INTERVAL = 2
SYMBOLS_CHECK_INTERVAL = 30


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
        self.last_api_call = {}
        self.last_symbols_check = 0

        # Verrous pour éviter les appels concurrents
        self.processing_symbols = set()

        # Limite de concurrence
        pool_size = getattr(config.database, 'pool_max_size', 20)
        reserve_connections = 3
        calculated_limit = max(5, min(15, pool_size - reserve_connections))
        if hasattr(config, 'performance') and hasattr(config.performance, 'max_concurrent_symbols'):
            self.max_concurrent_symbols = config.performance.max_concurrent_symbols
        else:
            self.max_concurrent_symbols = calculated_limit
        self.symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)

        log(f"Max concurrent symbols set to: {self.max_concurrent_symbols} (pool_max_size: {pool_size})", level="INFO")

        # Lazy-loaded handle_live_symbol function
        self._handle_live_symbol = None

    def _get_handle_live_symbol(self):
        if self._handle_live_symbol is None:
            self._handle_live_symbol = get_handle_live_symbol()
        return self._handle_live_symbol

    async def load_initial_positions(self):
        """
        Charge toutes les positions ouvertes existantes depuis Backpack Exchange
        au démarrage du dashboard.
        """
        try:
            positions = await get_real_positions(account)
            for pos in positions:
                self.open_positions[pos["symbol"]] = {
                    "symbol": pos["symbol"],
                    "side": pos.get("side", "N/A"),
                    "entry_price": pos.get("entry_price", 0.0),
                    "current_price": pos.get("entry_price", 0.0),
                    "pnl": 0.0,
                    "amount": pos.get("amount", 0.0),
                    "duration": "N/A",
                    "trailing_stop": 0.0,
                    "pnl_usdc": 0.0,
                    "ret_pct": 0.0,
                    "last_update": time.time(),
                    "status": "INACTIVE",
                }
            log(f"Loaded {len(self.open_positions)} open positions at startup", level="INFO")
        except Exception as e:
            log(f"Failed to load initial open positions: {e}", level="WARNING")

    # ---------------- SYMBOLS STATUS ----------------
    async def check_symbols_status(self):
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

    # ---------------- SYMBOL PROCESSING ----------------
    async def process_symbol_with_throttling(self, symbol):
        current_time = time.time()

        if symbol in self.last_api_call:
            time_since_last = current_time - self.last_api_call[symbol]
            if time_since_last < API_CALL_INTERVAL:
                return

        if symbol in self.processing_symbols:
            return

        async with self.symbol_semaphore:
            self.processing_symbols.add(symbol)
            try:
                self.last_api_call[symbol] = current_time
                result = await self.handle_live_symbol_with_pool(symbol)
                log(f"handle_live_symbol({symbol}) returned: {result}", level="DEBUG")

                # CORRECTION: Vérifier d'abord les positions réelles sur l'exchange
                try:
                    real_positions = await get_real_positions(account)
                    real_position = next((p for p in real_positions if p["symbol"] == symbol), None)
                except Exception as e:
                    log(f"Failed to get real positions for {symbol}: {e}", level="WARNING")
                    real_position = None

                if real_position:
                    # Position existe réellement sur l'exchange
                    if result:
                        # On a des données de trading, utiliser ces données
                        side = result.get("side", real_position.get("side", "N/A"))
                        entry = result.get("entry_price", real_position.get("entry_price", 0.0))
                        amount = result.get("amount", real_position.get("amount", 0.0))
                        pnl_pct = result.get("pnl", 0.0)
                        duration = result.get("duration", "0s")
                        trailing_stop = result.get("trailing_stop", 0.0)
                        
                        # Prix actuel
                        current_price = result.get("current_price", result.get("price", 0.0))
                        if current_price <= 0:
                            try:
                                market_info = await get_market(symbol)
                                if market_info:
                                    current_price = market_info.get("current_price", 0.0)
                            except Exception as e:
                                log(f"Failed to get current price for {symbol}: {e}", level="WARNING")
                                current_price = entry
                    else:
                        # Pas de données de trading mais position existe, utiliser les données réelles
                        side = real_position.get("side", "N/A")
                        entry = real_position.get("entry_price", 0.0)
                        amount = real_position.get("amount", 0.0)
                        duration = "N/A"  # Pas d'info de durée
                        trailing_stop = 0.0  # Pas de trailing stop actif
                        
                        # Calculer le PnL manuellement
                        try:
                            market_info = await get_market(symbol)
                            if market_info:
                                current_price = market_info.get("current_price", entry)
                            else:
                                current_price = entry
                            
                            if entry > 0 and current_price > 0:
                                if side.lower() == "long":
                                    pnl_pct = (current_price - entry) / entry * 100
                                elif side.lower() == "short":
                                    pnl_pct = (entry - current_price) / entry * 100
                                else:
                                    pnl_pct = 0.0
                            else:
                                pnl_pct = 0.0
                        except Exception as e:
                            log(f"Failed to calculate manual PnL for {symbol}: {e}", level="WARNING")
                            current_price = entry
                            pnl_pct = 0.0

                    # Calcul PnL$ et ret%
                    if entry > 0 and amount > 0 and current_price > 0:
                        if side.lower() == "long":
                            pnl_usdc = (current_price - entry) * amount
                            ret_pct = (current_price - entry) / entry * 100
                        elif side.lower() == "short":
                            pnl_usdc = (entry - current_price) * amount
                            ret_pct = (entry - current_price) / entry * 100
                        else:
                            pnl_usdc = 0.0
                            ret_pct = 0.0
                    else:
                        pnl_usdc = 0.0
                        ret_pct = 0.0
                        if entry <= 0 or amount <= 0 or current_price <= 0:
                            log(f"Warning: Invalid values for {symbol} - entry:{entry}, amount:{amount}, current_price:{current_price}", level="DEBUG")

                    # Stockage de la position
                    position_status = "ACTIVE" if result else "INACTIVE"
                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry,
                        "current_price": current_price,
                        "pnl": pnl_pct,
                        "amount": amount,
                        "duration": duration,
                        "trailing_stop": trailing_stop,
                        "pnl_usdc": pnl_usdc,
                        "ret_pct": ret_pct,
                        "last_update": current_time,
                        "status": position_status,
                    }

                    # Enregistrer les signaux de trading
                    if result:
                        action = result.get("signal", None)
                        if action in ["BUY", "SELL"]:
                            self.trade_events.append({
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "symbol": symbol,
                                "action": action,
                                "price": current_price
                            })
                            if len(self.trade_events) > 20:
                                self.trade_events = self.trade_events[-20:]

                else:
                    # Position n'existe plus sur l'exchange - vraiment fermée
                    if symbol in self.open_positions:
                        closed_position = self.open_positions[symbol]
                        log(f"Position really closed for {symbol} - Final PnL: {closed_position.get('pnl_usdc', 0):.2f}$", level="INFO")
                        
                        # Ajouter à l'historique des trades fermés
                        self.trade_events.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "symbol": symbol,
                            "action": "CLOSE",
                            "price": closed_position.get("current_price", 0),
                            "pnl": f"{closed_position.get('pnl_usdc', 0):.2f}$"
                        })
                        if len(self.trade_events) > 20:
                            self.trade_events = self.trade_events[-20:]
                        
                        del self.open_positions[symbol]

            except Exception as e:
                log(f"[ERROR] Impossible de traiter {symbol}: {e}", level="ERROR")
                if "too many clients" in str(e).lower():
                    self.last_api_call[symbol] = current_time + API_CALL_INTERVAL * 2
            finally:
                self.processing_symbols.discard(symbol)

    async def sync_with_exchange(self):
        """Synchronise les positions affichées avec celles réellement sur l'exchange"""
        try:
            real_positions = await get_real_positions(account)
            real_symbols = {p["symbol"] for p in real_positions}
            dashboard_symbols = set(self.open_positions.keys())
            
            # Positions qui ont été fermées mais pas encore supprimées du dashboard
            closed_positions = dashboard_symbols - real_symbols
            for symbol in closed_positions:
                if symbol in self.open_positions:
                    closed_position = self.open_positions[symbol]
                    log(f"Sync: Removing closed position from dashboard: {symbol} (Final PnL: {closed_position.get('pnl_usdc', 0):.2f}$)", level="INFO")
                    del self.open_positions[symbol]
            
            # Nouvelles positions qui ne sont pas dans le dashboard
            new_positions = real_symbols - dashboard_symbols
            for symbol in new_positions:
                log(f"Sync: New position detected on exchange: {symbol}", level="INFO")
                # Ajouter la nouvelle position avec des données de base
                real_position = next((p for p in real_positions if p["symbol"] == symbol), None)
                if real_position:
                    self.open_positions[symbol] = {
                        "symbol": symbol,
                        "side": real_position.get("side", "N/A"),
                        "entry_price": real_position.get("entry_price", 0.0),
                        "current_price": real_position.get("entry_price", 0.0),
                        "pnl": 0.0,
                        "amount": real_position.get("amount", 0.0),
                        "duration": "N/A",
                        "trailing_stop": 0.0,
                        "pnl_usdc": 0.0,
                        "ret_pct": 0.0,
                        "last_update": time.time(),
                        "status": "INACTIVE",
                    }
            
        except Exception as e:
            log(f"Failed to sync with exchange: {e}", level="WARNING")

    async def cleanup_stale_positions(self):
        """
        Supprime les positions qui n'ont pas été mises à jour depuis trop longtemps
        """
        current_time = time.time()
        stale_threshold = 300  # 5 minutes
        
        stale_symbols = []
        for symbol, position in self.open_positions.items():
            last_update = position.get("last_update", 0)
            if current_time - last_update > stale_threshold:
                stale_symbols.append(symbol)
        
        for symbol in stale_symbols:
            log(f"Removing stale position for {symbol} (no update for {stale_threshold}s)", level="INFO")
            del self.open_positions[symbol]

    async def handle_live_symbol_with_pool(self, symbol):
        try:
            handle_live_symbol = self._get_handle_live_symbol()
            result = await handle_live_symbol(symbol, self.pool, self.real_run, self.dry_run, args=self.args)
            return result
        except Exception as e:
            if "too many clients" in str(e).lower():
                log(f"[ERROR] Connection pool exhausted for {symbol}, will retry later", level="ERROR")
                await asyncio.sleep(API_CALL_INTERVAL)
            raise

    async def symbol_processor(self):
        while True:
            try:
                await self.check_symbols_status()
                
                # Synchronisation avec l'exchange toutes les 2 minutes
                if int(time.time()) % 120 == 0:
                    await self.sync_with_exchange()
                
                # Nettoyage périodique des positions obsolètes
                if int(time.time()) % 60 == 0:
                    await self.cleanup_stale_positions()
                
                active_symbols = self.active_symbols
                total_symbols = len(active_symbols)

                if total_symbols > self.max_concurrent_symbols:
                    current_batch = int(time.time() // (API_CALL_INTERVAL * 2)) % ((total_symbols // self.max_concurrent_symbols) + 1)
                    start_idx = current_batch * self.max_concurrent_symbols
                    end_idx = min(start_idx + self.max_concurrent_symbols, total_symbols)
                    active_symbols = active_symbols[start_idx:end_idx]
                    log(f"Processing batch {current_batch + 1}: symbols {start_idx+1}-{end_idx} of {total_symbols} total", level="DEBUG")
                else:
                    log(f"Processing all {total_symbols} active symbols", level="DEBUG")

                tasks = []
                for i, symbol in enumerate(active_symbols):
                    delay = (i * API_CALL_INTERVAL) / len(active_symbols) if active_symbols else 0
                    task = asyncio.create_task(self._process_symbol_delayed(symbol, delay))
                    tasks.append(task)

                if tasks:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*tasks, return_exceptions=True),
                            timeout=API_CALL_INTERVAL * 2
                        )
                    except asyncio.TimeoutError:
                        log("Some API calls timed out, continuing...", level="WARNING")

                await asyncio.sleep(max(1, API_CALL_INTERVAL // 2))
            except Exception as e:
                log(f"[ERROR] Erreur dans symbol_processor: {e}", level="ERROR")
                await asyncio.sleep(5)

    async def _process_symbol_delayed(self, symbol, delay):
        if delay > 0:
            await asyncio.sleep(delay)
        await self.process_symbol_with_throttling(symbol)

    def format_pnl_with_color(self, pnl_value, pnl_str):
        """Formate le PnL avec des couleurs (vert pour positif, rouge pour négatif)"""
        if pnl_value > 0:
            return f"\033[92m{pnl_str}\033[0m"  # Vert
        elif pnl_value < 0:
            return f"\033[91m{pnl_str}\033[0m"  # Rouge
        else:
            return f"\033[93m{pnl_str}\033[0m"  # Jaune pour 0

    def calculate_performance_stats(self):
        """Calcule des statistiques de performance"""
        if not self.open_positions:
            return {}
        
        positions = list(self.open_positions.values())
        pnl_values = [p.get("pnl_usdc", 0.0) for p in positions]
        
        return {
            "total_pnl": sum(pnl_values),
            "avg_pnl": sum(pnl_values) / len(pnl_values),
            "best_position": max(pnl_values),
            "worst_position": min(pnl_values),
            "profitable_positions": len([p for p in pnl_values if p > 0]),
            "losing_positions": len([p for p in pnl_values if p < 0]),
            "total_positions": len(positions)
        }

    def check_alerts(self):
        """Vérifie les alertes sur les positions"""
        alerts = []
        
        for symbol, position in self.open_positions.items():
            pnl = position.get("pnl", 0.0)
            pnl_usd = position.get("pnl_usdc", 0.0)
            
            # Alerte pour les grosses pertes
            if pnl < -10:
                alerts.append(f"🚨 {symbol}: Large loss {pnl:.2f}% ({pnl_usd:.2f}$)")
            
            # Alerte pour les gros gains
            elif pnl > 15:
                alerts.append(f"🚀 {symbol}: Large gain {pnl:.2f}% ({pnl_usd:.2f}$)")
            
            # Alerte si pas de trailing stop sur position profitable
            elif pnl > 5 and position.get("trailing_stop", 0.0) == 0:
                alerts.append(f"⚠️ {symbol}: No trailing stop on +{pnl:.2f}% position")
        
        return alerts

    # ---------------- DASHBOARD RENDER ----------------
    async def render_dashboard(self):
        while True:
            try:
                await asyncio.sleep(DASHBOARD_REFRESH_INTERVAL)
                os.system("clear")

                print(f"=== CONFIGURATION ===")
                print(f"API Call Interval: {API_CALL_INTERVAL}s")
                print(f"Dashboard Refresh: {DASHBOARD_REFRESH_INTERVAL}s")
                print(f"Symbols Check: {SYMBOLS_CHECK_INTERVAL}s\n")

                print("=== SYMBOLS ===")
                print(tabulate([
                    ["Active", f"{len(self.active_symbols)} symbols: {', '.join(self.active_symbols[:10])}{' ...' if len(self.active_symbols) > 10 else ''}"],
                    ["Ignored", f"{len(self.ignored_symbols)} symbols: {', '.join(self.ignored_symbols[:10])}{' ...' if len(self.ignored_symbols) > 10 else ''}"]
                ], headers=["Status", "Symbols"], tablefmt="fancy_grid"))

                print("\n=== API CALL STATUS ===")
                current_time = time.time()
                api_status = []
                max_symbols = config.performance.max_concurrent_symbols

                for symbol in self.active_symbols[:max_symbols]:
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

                print("\n=== TRADE EVENTS ===")
                if self.trade_events:
                    print(tabulate(self.trade_events[-10:], headers="keys", tablefmt="fancy_grid"))
                else:
                    print("No trades yet.")

                print("\n=== OPEN POSITIONS ===")
                if self.open_positions:
                    positions_data = []
                    total_pnl_usd = 0
                    
                    for p in self.open_positions.values():
                        pnl_usd = p.get("pnl_usdc", 0.0)
                        total_pnl_usd += pnl_usd
                        
                        # Indicateur de statut
                        status_indicator = "🟢" if p.get("status") == "ACTIVE" else "🟡"
                        
                        positions_data.append([
                            f"{status_indicator} {p.get('symbol', 'N/A')}",
                            p.get("side", "N/A"),
                            f'{p.get("entry_price", 0.0):.6f}',
                            f'{p.get("current_price", 0.0):.6f}',
                            self.format_pnl_with_color(p.get("pnl", 0.0), f'{p.get("pnl", 0.0):.2f}%'),
                            self.format_pnl_with_color(pnl_usd, f'{pnl_usd:.2f}$'),
                            self.format_pnl_with_color(p.get("ret_pct", 0.0), f'({p.get("ret_pct", 0.0):.2f}%)'),
                            p.get("amount", 0.0),
                            p.get("duration", "0s"),
                            f'{p.get("trailing_stop", 0.0):.2f}%'
                        ])
                    
                    print(tabulate(
                        positions_data,
                        headers=["Symbol", "Side", "Entry", "Current", "PnL%", "PnL$", "ret%", "Amount", "Duration", "Trailing Stop"],
                        tablefmt="fancy_grid"
                    ))
                    
                    # Afficher le total PnL
                    total_color = self.format_pnl_with_color(total_pnl_usd, f"Total PnL: {total_pnl_usd:.2f}$")
                    print(f"\n{total_color}")
                    print("\n🟢 Active (bot trading) | 🟡 Inactive (position open but no bot signal)")
                else:
                    print("No open positions yet.")

                # Statistiques de performance
                print(f"\n=== PERFORMANCE ===")
                perf_stats = self.calculate_performance_stats()
                if perf_stats:
                    print(f"Total PnL: {self.format_pnl_with_color(perf_stats['total_pnl'], f'{perf_stats[\"total_pnl\"]:.2f}
                    print(f"Average PnL: {perf_stats['avg_pnl']:.2f}$")
                    print(f"Best position: +{perf_stats['best_position']:.2f}$")
                    print(f"Worst position: {perf_stats['worst_position']:.2f}$")
                    print(f"Win rate: {perf_stats['profitable_positions']}/{perf_stats['total_positions']} ({perf_stats['profitable_positions']/perf_stats['total_positions']*100:.1f}%)")

                # Alertes
                print(f"\n=== ALERTS ===")
                alerts = self.check_alerts()
                if alerts:
                    for alert in alerts:
                        print(alert)
                else:
                    print("No alerts.")

                print(f"\n=== STATS ===")
                print(f"Total symbols: {len(self.active_symbols + self.ignored_symbols)}")
                print(f"Active symbols: {len(self.active_symbols)}")
                print(f"Ignored symbols: {len(self.ignored_symbols)}")
                print(f"Max concurrent processing: {self.max_concurrent_symbols}")
                print(f"Total API calls tracked: {len(self.last_api_call)}")
                print(f"Symbols currently processing: {len(self.processing_symbols)}")
                print(f"Pool size: {config.database.pool_min_size}-{config.database.pool_max_size}")
                print(f"Last symbols check: {int(current_time - self.last_symbols_check)}s ago")

                if len(self.active_symbols) > self.max_concurrent_symbols:
                    total_batches = (len(self.active_symbols) // self.max_concurrent_symbols) + 1
                    current_batch = int(current_time // (API_CALL_INTERVAL * 2)) % total_batches
                    print(f"Batch rotation: {current_batch + 1}/{total_batches} (changes every {API_CALL_INTERVAL * 2}s)")

            except Exception as e:
                log(f"Erreur dans render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)

async def refresh_dashboard():
    """
    Récupère et affiche toutes les positions ouvertes au format tableau avec PnL$ et ret%.
    """
    positions = await get_real_positions(account)
    if not positions:
        log("[INFO] No open positions at this time")
        return

    table_data = []
    for p in positions:
        symbol = p["symbol"]
        market_info = await get_market(symbol)
        if market_info is None:
            continue

        current_price = market_info.get("current_price", p["entry_price"])
        entry_price = market_info.get("entry_price", p["entry_price"])
        side = market_info.get("side", p["side"])
        amount = p["amount"]

        # PnL en pourcentage déjà calculé
        pnl_percent = market_info.get("pnl", 0.0)

        # PnL$ selon la direction
        if side == "long":
            pnl_usd = (current_price - entry_price) * amount
        else:  # short
            pnl_usd = (entry_price - current_price) * amount

        # ret% (retour en % sur l'investissement)
        try:
            ret_percent = pnl_usd / (entry_price * amount) * 100
        except ZeroDivisionError:
            ret_percent = 0.0

        table_data.append([
            symbol,
            side,
            f"{entry_price:.6f}",
            f"{pnl_percent:.2f}%",
            f"{pnl_usd:.2f}$",
            f"({ret_percent:.2f}%)",
            amount,
            p["duration"],
            f"{p.get('trailing_stop', 0.0):.2f}%"
        ])

    table = tabulate(
        table_data,
        headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "ret%", "Amount", "Duration", "Trailing Stop"],
        tablefmt="pretty"
    )
    log("\n" + table))}")
                    print(f"Average PnL: {perf_stats['avg_pnl']:.2f}$")
                    print(f"Best position: +{perf_stats['best_position']:.2f}$")
                    print(f"Worst position: {perf_stats['worst_position']:.2f}$")
                    print(f"Win rate: {perf_stats['profitable_positions']}/{perf_stats['total_positions']} ({perf_stats['profitable_positions']/perf_stats['total_positions']*100:.1f}%)")

                # Alertes
                print(f"\n=== ALERTS ===")
                alerts = self.check_alerts()
                if alerts:
                    for alert in alerts:
                        print(alert)
                else:
                    print("No alerts.")

                print(f"\n=== STATS ===")
                print(f"Total symbols: {len(self.active_symbols + self.ignored_symbols)}")
                print(f"Active symbols: {len(self.active_symbols)}")
                print(f"Ignored symbols: {len(self.ignored_symbols)}")
                print(f"Max concurrent processing: {self.max_concurrent_symbols}")
                print(f"Total API calls tracked: {len(self.last_api_call)}")
                print(f"Symbols currently processing: {len(self.processing_symbols)}")
                print(f"Pool size: {config.database.pool_min_size}-{config.database.pool_max_size}")
                print(f"Last symbols check: {int(current_time - self.last_symbols_check)}s ago")

                if len(self.active_symbols) > self.max_concurrent_symbols:
                    total_batches = (len(self.active_symbols) // self.max_concurrent_symbols) + 1
                    current_batch = int(current_time // (API_CALL_INTERVAL * 2)) % total_batches
                    print(f"Batch rotation: {current_batch + 1}/{total_batches} (changes every {API_CALL_INTERVAL * 2}s)")

            except Exception as e:
                log(f"Erreur dans render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)

async def refresh_dashboard():
    """
    Récupère et affiche toutes les positions ouvertes au format tableau avec PnL$ et ret%.
    """
    positions = await get_real_positions(account)
    if not positions:
        log("[INFO] No open positions at this time")
        return

    table_data = []
    for p in positions:
        symbol = p["symbol"]
        market_info = await get_market(symbol)
        if market_info is None:
            continue

        current_price = market_info.get("current_price", p["entry_price"])
        entry_price = market_info.get("entry_price", p["entry_price"])
        side = market_info.get("side", p["side"])
        amount = p["amount"]

        # PnL en pourcentage déjà calculé
        pnl_percent = market_info.get("pnl", 0.0)

        # PnL$ selon la direction
        if side == "long":
            pnl_usd = (current_price - entry_price) * amount
        else:  # short
            pnl_usd = (entry_price - current_price) * amount

        # ret% (retour en % sur l'investissement)
        try:
            ret_percent = pnl_usd / (entry_price * amount) * 100
        except ZeroDivisionError:
            ret_percent = 0.0

        table_data.append([
            symbol,
            side,
            f"{entry_price:.6f}",
            f"{pnl_percent:.2f}%",
            f"{pnl_usd:.2f}$",
            f"({ret_percent:.2f}%)",
            amount,
            p["duration"],
            f"{p.get('trailing_stop', 0.0):.2f}%"
        ])

    table = tabulate(
        table_data,
        headers=["Symbol", "Side", "Entry", "PnL%", "PnL$", "ret%", "Amount", "Duration", "Trailing Stop"],
        tablefmt="pretty"
    )
    log("\n" + table)