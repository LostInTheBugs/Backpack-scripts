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
            
            # Récupère les symboles auto, force à [] si None
            auto_symbols = fetch_top_n_volatility_volume(
                n=getattr(config.strategy, "auto_select_top_n", 10)
            ) or []

            # Sécurité : s'assurer qu'on a bien une liste
            if not isinstance(auto_symbols, list):
                log(f"[WARNING] ⚠️ auto_symbols n'est pas une liste: {auto_symbols}, remplacement par []", level="WARNING")
                auto_symbols = []

            # Merge avec la configuration (includes/excludes)
            symbols = merge_symbols_with_config(auto_symbols) or []

            # Sécurité : merge peut renvoyer None ou type inattendu
            if not isinstance(symbols, list):
                log(f"[WARNING] ⚠️ merge_symbols_with_config a renvoyé un type inattendu ({type(symbols)}), remplacement par []", level="WARNING")
                symbols = []

            # Met à jour le container partagé
            symbols_container['list'] = symbols

            log(f"[INFO] ✅ Symboles mis à jour : {symbols}", level="INFO")

        except Exception as e:
            log(f"[ERROR] ❌ Erreur mise à jour symboles : {e}", level="ERROR")

        time.sleep(interval)
