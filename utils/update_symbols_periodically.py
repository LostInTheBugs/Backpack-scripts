import time
import threading
from utils.logger import log
from config.settings import get_config
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume

config = get_config()

def merge_symbols_with_config(auto_symbols: list) -> list:
    """Fusionne auto-select avec include, puis enlève exclude."""
    include_list = [s.upper() for s in getattr(config.symbols, "include", [])]
    exclude_list = [s.upper() for s in getattr(config.symbols, "exclude", [])]

    # Normaliser les auto_symbols
    symbols_upper = [s.upper() for s in auto_symbols]

    # Ajouter tous les includes absents
    for s in include_list:
        if s not in symbols_upper:
            auto_symbols.append(s)

    # Retirer les excludes
    final_symbols = [s for s in auto_symbols if s.upper() not in exclude_list]

    return final_symbols

def update_symbols_periodically(symbols_container: dict):
    interval = getattr(config.strategy, "auto_select_update_interval", 300)

    while True:
        try:
            log("[INFO] 🔄 Mise à jour des symboles...", level="INFO")
            auto_symbols = fetch_top_n_volatility_volume(
                n=config.strategy.auto_select_top_n
            )
            symbols = merge_symbols_with_config(auto_symbols)
            symbols_container['list'] = symbols
            log(f"[INFO] ✅ Symboles mis à jour : {symbols}", level="INFO")
        except Exception as e:
            log(f"[ERROR] ❌ Erreur mise à jour symboles : {e}", level="ERROR")
        time.sleep(interval)

def start_symbol_updater(symbols_container: dict):
    t = threading.Thread(
        target=update_symbols_periodically,
        args=(symbols_container,),
        daemon=True
    )
    t.start()
    log("[INFO] 🚀 Thread de mise à jour des symboles démarré", level="INFO")
