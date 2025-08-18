import time
import threading
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
    def _update_loop():
        interval = getattr(config.strategy, "auto_select_update_interval", 300)
        log(f"[DEBUG] 🕐 Démarrage du thread de mise à jour des symboles (intervalle: {interval}s)", level="DEBUG")

        while True:
            try:
                log("[INFO] 🔄 Mise à jour des symboles...", level="INFO")
                
                # Récupère les symboles auto avec gestion d'erreur robuste
                try:
                    auto_symbols = fetch_top_n_volatility_volume(
                        n=getattr(config.strategy, "auto_select_top_n", 10)
                    )
                    
                    # Force à [] si None ou type inattendu
                    if auto_symbols is None:
                        log("[WARNING] ⚠️ fetch_top_n_volatility_volume a retourné None", level="WARNING")
                        auto_symbols = []
                    elif not isinstance(auto_symbols, list):
                        log(f"[WARNING] ⚠️ fetch_top_n_volatility_volume a retourné un type inattendu: {type(auto_symbols)}, conversion en liste", level="WARNING")
                        auto_symbols = list(auto_symbols) if auto_symbols else []
                        
                except Exception as e:
                    log(f"[ERROR] ❌ Erreur lors de la récupération des auto_symbols : {e}", level="ERROR")
                    auto_symbols = []

                log(f"[DEBUG] 📊 Auto symbols récupérés : {auto_symbols}", level="DEBUG")

                # Merge avec la configuration (includes/excludes) avec gestion d'erreur robuste
                try:
                    symbols = merge_symbols_with_config(auto_symbols)
                    
                    # Gestion du cas où merge_symbols_with_config retourne None
                    if symbols is None:
                        log("[WARNING] ⚠️ merge_symbols_with_config a retourné None, utilisation des auto_symbols", level="WARNING")
                        symbols = auto_symbols
                    elif not isinstance(symbols, list):
                        log(f"[WARNING] ⚠️ merge_symbols_with_config a retourné un type inattendu ({type(symbols)}), conversion en liste", level="WARNING")
                        symbols = list(symbols) if symbols else []
                        
                except Exception as e:
                    log(f"[ERROR] ❌ Erreur lors du merge avec la config : {e}, utilisation des auto_symbols", level="ERROR")
                    symbols = auto_symbols

                # Double vérification de sécurité
                if not isinstance(symbols, list):
                    log(f"[ERROR] ❌ Après toutes les vérifications, symbols n'est toujours pas une liste: {type(symbols)}", level="ERROR")
                    symbols = []

                # Met à jour le container partagé de manière thread-safe
                if symbols_container is not None and isinstance(symbols_container, dict):
                    symbols_container['list'] = symbols
                    log(f"[INFO] ✅ Symboles mis à jour ({len(symbols)}): {symbols}", level="INFO")
                else:
                    log("[ERROR] ❌ symbols_container invalide ou None", level="ERROR")

            except Exception as e:
                log(f"[ERROR] ❌ Erreur inattendue dans la mise à jour des symboles : {e}", level="ERROR")
                import traceback
                log(f"[ERROR] Stack trace: {traceback.format_exc()}", level="ERROR")
                
                # En cas d'erreur critique, s'assurer que le container a au moins une liste vide
                if symbols_container is not None and isinstance(symbols_container, dict):
                    if 'list' not in symbols_container or symbols_container['list'] is None:
                        symbols_container['list'] = []

            # Attendre l'intervalle avant la prochaine mise à jour
            time.sleep(interval)

    # Créer et lancer le thread daemon
    thread = threading.Thread(target=_update_loop, daemon=True, name="SymbolsUpdater")
    thread.start()
    log("[INFO] 🚀 Thread de mise à jour des symboles démarré", level="INFO")
    return thread


def manual_update_symbols(symbols_container: dict):
    """
    Met à jour manuellement les symboles (pour tests ou usage ponctuel).
    
    :param symbols_container: dict partagé pour stocker la liste des symboles
    :return: list des symboles mis à jour
    """
    try:
        log("[INFO] 🔄 Mise à jour manuelle des symboles...", level="INFO")
        
        auto_symbols = fetch_top_n_volatility_volume(
            n=getattr(config.strategy, "auto_select_top_n", 10)
        ) or []
        
        if not isinstance(auto_symbols, list):
            auto_symbols = []
            
        symbols = merge_symbols_with_config(auto_symbols)
        
        if symbols is None or not isinstance(symbols, list):
            symbols = auto_symbols
            
        symbols_container['list'] = symbols
        
        log(f"[INFO] ✅ Mise à jour manuelle terminée : {symbols}", level="INFO")
        return symbols
        
    except Exception as e:
        log(f"[ERROR] ❌ Erreur lors de la mise à jour manuelle : {e}", level="ERROR")
        symbols_container['list'] = []
        return []