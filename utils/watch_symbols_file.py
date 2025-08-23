# utils/watch_symbols_file.py - VERSION DEBUG
import os
import asyncio
from utils.logger import log
from utils.public import load_symbols_from_file
from utils.symbol_filter import filter_symbols_by_config
from utils.i18n import t

async def watch_symbols_file(filepath: str = "symbol.lst", pool=None, real_run=False, dry_run=False):
    last_modified = None
    symbols = []
    
    log(f"🔍 DEBUG: Starting watcher for {filepath}", level="DEBUG")

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                log(f"🔍 DEBUG: File modified, reloading symbols", level="DEBUG")
                
                # Debug: étape par étape
                symbols_raw = load_symbols_from_file(filepath)
                log(f"🔍 DEBUG: load_symbols_from_file returned: {symbols_raw} (type: {type(symbols_raw)})", level="DEBUG")
                
                if symbols_raw is None:
                    symbols_raw = []
                    log(f"⚠️ load_symbols_from_file returned None, using empty list", level="WARNING")
                
                symbols_filtered = filter_symbols_by_config(symbols_raw)
                log(f"🔍 DEBUG: filter_symbols_by_config returned: {symbols_filtered} (type: {type(symbols_filtered)})", level="DEBUG")
                
                if symbols_filtered is None:
                    symbols_filtered = []
                    log(f"⚠️ filter_symbols_by_config returned None, using empty list", level="WARNING")
                
                symbols = symbols_filtered
                log(f"🔍 DEBUG: Final symbols list: {symbols} (length: {len(symbols)})", level="DEBUG")
                
                # Test d'itération pour détecter le problème
                try:
                    for i, symbol in enumerate(symbols):
                        log(f"🔍 DEBUG: Symbol {i}: {symbol}", level="DEBUG")
                        if i >= 2:  # Limiter le debug aux 3 premiers
                            break
                except Exception as iter_error:
                    log(f"❌ DEBUG: Iteration error: {iter_error}", level="ERROR")
                    log(f"❌ DEBUG: symbols type at iteration: {type(symbols)}", level="ERROR")
                    symbols = []  # Forcer une liste vide en cas d'erreur
                
                log(t("symbols.file_reloaded", symbols))
                last_modified = current_modified
            
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            log("🛑 KeyboardInterrupt caught in watcher", level="INFO")
            break
        except Exception as e:
            log(f"💥 Erreur dans le watcher : {e}", level="ERROR")
            log(f"💥 DEBUG: Exception type: {type(e)}", level="ERROR")
            import traceback
            log(f"💥 DEBUG: Traceback: {traceback.format_exc()}", level="ERROR")
            # Pause pour éviter le spam d'erreurs
            await asyncio.sleep(5)