import asyncio
from utils.public import check_table_and_fresh_data  # ou autre fonction utile
from utils.logger import log

async def scan_all_symbols(pool, symbols):
    log(f"🔎 Scan initial de {len(symbols)} symboles...", level="DEBUG")
    for symbol in symbols:
        # Par exemple : tu vérifies que les tables / données existent pour chaque symbole
        # ou tu déclenches une récupération initiale de données
        try:
            # Exemple simple (à adapter selon ton code)
            exists = await check_table_and_fresh_data(pool, symbol, max_age_seconds=3600)
            if not exists:
                log(f"Données manquantes pour {symbol}, déclenche récupération", level="DEBUG")
                # ici appelle ta fonction de récupération si besoin
        except Exception as e:
            log(f"Erreur lors du scan initial {symbol}: {e}", level="ERROR")
    log(f"✅ Scan initial terminé.", level="DEBUG")
