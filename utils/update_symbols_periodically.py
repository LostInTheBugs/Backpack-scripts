import time
from utils.logger import log
from config.settings import get_config
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from utils.public import merge_symbols_with_config

config = get_config()

def update_symbols_periodically(symbols_container: dict):
    """
    Thread qui met à jour périodiquement la liste des symboles.
    Protège contre None ou erreurs lors de la récupération.

    :param symbols_container: dict partagé pour stocker la liste des symboles
    """
    interval = getattr(config.strategy, "auto_select_update_interval", 300)

    while True:
        try:
            log("[INFO] 🔄 Mise à jour des symboles...", level="INFO")
            
            # Récupère les symboles auto
            try:
                auto_symbols = fetch_top_n_volatility_volume(
                    n=getattr(config.strategy, "auto_select_top_n", 10)
                )
                if not isinstance(auto_symbols, (list, tuple)):
                    log(f"[WARNING] ⚠️ fetch_top_n_volatility_volume a renvoyé un type inattendu ({type(auto_symbols)}), remplacement par []", level="WARNING")
                    auto_symbols = []
            except Exception as inner_e:
                log(f"[ERROR] ❌ Erreur interne lors de fetch_top_n_volatility_volume: {inner_e}", level="ERROR")
                auto_symbols = []

            # Merge avec la configuration (includes/excludes)
            try:
                symbols = merge_symbols_with_config(auto_symbols or [])
            except Exception as merge_e:
                log(f"[ERROR] ❌ Erreur merge_symbols_with_config: {merge_e}", level="ERROR")
                symbols = []

            # Met à jour le container partagé
            symbols_container['list'] = symbols

            log(f"[INFO] ✅ Symboles mis à jour : {symbols}", level="INFO")

        except Exception as e:
            log(f"[ERROR] ❌ Erreur inattendue dans update_symbols_periodically : {e}", level="ERROR")

        time.sleep(interval)

# Alias pour compatibilité main.py
start_symbol_updater = update_symbols_periodically
