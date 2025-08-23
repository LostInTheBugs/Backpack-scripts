# utils/watch_symbols_file.py
import os
import asyncio
from utils.logger import log
from utils.public import load_symbols_from_file
from utils.symbol_filter import filter_symbols_by_config
from utils.i18n import t

async def watch_symbols_file(filepath: str = "symbol.lst", pool=None, real_run=False, dry_run=False):
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                # ✅ CORRECTION: Protection contre None
                symbols = load_symbols_from_file(filepath)
                if symbols is None:
                    symbols = []
                    log(f"⚠️ load_symbols_from_file returned None, using empty list", level="WARNING")
                
                symbols = filter_symbols_by_config(symbols)
                if symbols is None:
                    symbols = []
                    log(f"⚠️ filter_symbols_by_config returned None, using empty list", level="WARNING")
                
                # ✅ AMÉLIORATION: Message i18n
                log(t("symbols.file_reloaded", symbols))
                last_modified = current_modified
            
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            log(t("system.manual_stop"), level="INFO")
            break
        except Exception as e:
            log(t("system.watcher_error", e), level="ERROR")