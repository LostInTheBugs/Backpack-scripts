# utils/watch_symbols_file.py
import os
import asyncio
from utils.logger import log
from utils.public import load_symbols_from_file
from utils.symbol_filter import filter_symbols_by_config

async def watch_symbols_file(filepath: str = "symbol.lst", pool=None, real_run=False, dry_run=False):
    last_modified = None
    symbols = []

    while True:
        try:
            current_modified = os.path.getmtime(filepath)
            if current_modified != last_modified:
                symbols = load_symbols_from_file(filepath)
                symbols = filter_symbols_by_config(symbols)
                log(f"Symbol file reloaded: {symbols}")
                last_modified = current_modified
            
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            log("Manual stop requested", level="INFO")
            break
        except Exception as e:
            log(f"Error in watcher: {e}", level="ERROR")