import time
from utils.logger import log
from config.settings import get_config
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from utils.public import merge_symbols_with_config

config = get_config()

def update_symbols_periodically(symbols_container: dict):
    """
    Thread qui met à jour périodiquement la liste des symboles.

    :param symbols_container: dict partagé pour stocker la liste des symboles
    """
    interval = getattr(config.strategy, "auto_select_update_interval", 300)

    while True:
        try:
            log("[INFO] 🔄 Mise à jour des symboles...", level="INFO")
            
            # Récupère les symboles auto
            auto_symbols = fetch_top_n_volatility_volume(
                n=getattr(config.strategy, "auto_select_top_n", 10)
            )

            # ✅ Protection contre None
            if not auto_symbols:
                log("[WARNING] ⚠️ Aucun symbole récupéré, auto_symbols remplacé par []", level="WARNING")
                auto_symbols = []

            # Merge avec la configuration (includes/excludes)
            symbols = merge_symbols_with_config(auto_symbols)

            # Met à jour le container partagé
            symbols_container['list'] = symbols

            log(f"[INFO] ✅ Symboles mis à jour : {symbols}", level="INFO")

        except Exception as e:
            log(f"[ERROR] ❌ Erreur mise à jour symboles : {e}", level="ERROR")

        time.sleep(interval)
