#dashboard/textdashboard.py
import asyncio
import time
import os

from tabulate import tabulate
from datetime import datetime, timezone
from utils.public import check_table_and_fresh_data
from live.live_engine import get_handle_live_symbol
from utils.logger import log
from config.settings import load_config

config = load_config()
# Configuration des intervalles (en secondes) - avec valeurs par défaut
API_CALL_INTERVAL = 5  # Minimum entre appels API par symbole
DASHBOARD_REFRESH_INTERVAL = 2  # Rafraîchissement du dashboard
SYMBOLS_CHECK_INTERVAL = 30  # Vérification du statut des symboles


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
        # Calcul plus intelligent de la limite basé sur la config
        pool_size = getattr(config.database, 'pool_max_size', 20)
        reserve_connections = 3  # Réserver 3 connexions pour autres opérations
        calculated_limit = max(5, min(15, pool_size - reserve_connections))  # Entre 5 et 15
        
        # Permettre override via config si disponible
        if hasattr(config, 'performance') and hasattr(config.performance, 'max_concurrent_symbols'):
            self.max_concurrent_symbols = config.performance.max_concurrent_symbols
        else:
            self.max_concurrent_symbols = calculated_limit
            
        self.symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)
        
        log(f"Max concurrent symbols set to: {self.max_concurrent_symbols} (pool_max_size: {pool_size})", level="INFO")
        
        # Lazy-loaded handle_live_symbol function
        self._handle_live_symbol = None
        
    def _get_handle_live_symbol(self):
        """Get handle_live_symbol function with lazy loading"""
        if self._handle_live_symbol is None:
            self._handle_live_symbol = get_handle_live_symbol()
        return self._handle_live_symbol
        
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
            # Use lazy-loaded function to avoid circular import
            handle_live_symbol = self._get_handle_live_symbol()
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
                
                # Gestion intelligente des symboles actifs
                active_symbols = self.active_symbols
                total_symbols = len(active_symbols)
                
                if total_symbols > self.max_concurrent_symbols:
                    # Option 1: Rotation des symboles pour traiter tous les symboles à tour de rôle
                    current_batch = int(time.time() // (API_CALL_INTERVAL * 2)) % ((total_symbols // self.max_concurrent_symbols) + 1)
                    start_idx = current_batch * self.max_concurrent_symbols
                    end_idx = min(start_idx + self.max_concurrent_symbols, total_symbols)
                    active_symbols = active_symbols[start_idx:end_idx]
                    
                    log(f"Processing batch {current_batch + 1}: symbols {start_idx+1}-{end_idx} of {total_symbols} total", level="INFO")
                else:
                    log(f"Processing all {total_symbols} active symbols", level="DEBUG")
                
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
                print(f"Total symbols: {len(self.active_symbols + self.ignored_symbols)}")
                print(f"Active symbols: {len(self.active_symbols)}")
                print(f"Ignored symbols: {len(self.ignored_symbols)}")
                print(f"Max concurrent processing: {self.max_concurrent_symbols}")
                print(f"Total API calls tracked: {len(self.last_api_call)}")
                print(f"Symbols currently processing: {len(self.processing_symbols)}")
                print(f"Pool size: {config.database.pool_min_size}-{config.database.pool_max_size}")
                print(f"Last symbols check: {int(current_time - self.last_symbols_check)}s ago")
                
                # Afficher les symboles par batch si nécessaire
                if len(self.active_symbols) > self.max_concurrent_symbols:
                    total_batches = (len(self.active_symbols) // self.max_concurrent_symbols) + 1
                    current_batch = int(current_time // (API_CALL_INTERVAL * 2)) % total_batches
                    print(f"Batch rotation: {current_batch + 1}/{total_batches} (changes every {API_CALL_INTERVAL * 2}s)")
                
            except Exception as e:
                log(f"[ERROR] Erreur dans render_dashboard: {e}", level="ERROR")
                await asyncio.sleep(5)


async def main_loop_textdashboard(symbols: list, pool, real_run: bool, dry_run: bool, symbols_container=None, args=None):
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
