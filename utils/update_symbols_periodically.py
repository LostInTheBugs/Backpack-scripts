import time
import threading
from utils.logger import log
from config.settings import get_config

config = get_config()

def filter_symbols_by_config(symbols: list) -> list:
    include_list = getattr(config.symbols, "include", [])
    exclude_list = getattr(config.symbols, "exclude", [])

    include_list = [s.upper() for s in include_list]
    exclude_list = [s.upper() for s in exclude_list]

    if include_list:
        filtered = [s for s in symbols if s.upper() in include_list]
        for s in include_list:
            if s not in filtered:
                filtered.append(s)
    else:
        filtered = symbols.copy()

    filtered = [s for s in filtered if s.upper() not in exclude_list]
    return filtered

def update_symbols_periodically(symbols_container: dict):
    from utils.symbols import get_top_symbols
    interval = getattr(config.strategy, "auto_select_update_interval", 300)

    while True:
        try:
            log("🔄 Mise à jour des symboles...")
            symbols = get_top_symbols(top_n=config.strategy.auto_select_top_n)
            symbols = filter_symbols_by_config(symbols)
            symbols_container['list'] = symbols  # Mise à jour dans le dict partagé
            log(f"✅ Symboles mis à jour : {symbols}")
        except Exception as e:
            log(f"❌ Erreur mise à jour symboles : {e}")
        time.sleep(interval)

def start_symbol_updater(symbols_container: dict):
    t = threading.Thread(target=update_symbols_periodically, args=(symbols_container,), daemon=True)
    t.start()
    log("🚀 Thread de mise à jour des symboles démarré")
