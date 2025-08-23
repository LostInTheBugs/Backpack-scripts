#!/usr/bin/env python3
"""
Script de migration automatique des messages hardcodés vers i18n
Usage: python migrate_to_i18n.py live/live_engine.py
"""

import re
import sys
from pathlib import Path

# Patterns de remplacement pour live/live_engine.py
REPLACEMENTS = [
    # Trailing stop
    {
        'pattern': r'log\(f"\[{symbol}\] 🎯 Trailing stop initialized at {(\w+):.1f}%", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.trailing_stop.initialized", symbol=symbol, percentage=\1), level="DEBUG")',
        'key': 'live_engine.trailing_stop.initialized'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 📈 Trailing stop updated: {(\w+):.1f}% → {(\w+)\[(\w+)\]:.1f}%", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.trailing_stop.updated", symbol=symbol, prev=\1, new=\2[\3]), level="DEBUG")',
        'key': 'live_engine.trailing_stop.updated'
    },
    
    # Indicateurs
    {
        'pattern': r'log\(f"\[{symbol}\] ✅ RSI récupéré via API: {(\w+):.2f}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.indicators.rsi_retrieved", symbol=symbol, rsi=\1), level="DEBUG")',
        'key': 'live_engine.indicators.rsi_retrieved'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ✅ MACD calculé automatiquement\.", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.indicators.macd_calculated", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.indicators.macd_calculated'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ Erreur RSI API, tentative calcul local: {(\w+)}", level="WARNING"\)',
        'replacement': r'log(t("live_engine.indicators.rsi_error_fallback", symbol=symbol, error=\1), level="WARNING")',
        'key': 'live_engine.indicators.rsi_error_fallback'
    },
    
    # Données
    {
        'pattern': r'log\(f"\[{symbol}\] 📈 Loading OHLCV data for {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.data.loading", symbol=symbol, interval=\1), level="DEBUG")',
        'key': 'live_engine.data.loading'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Ignored: no recent data in local database", level="ERROR"\)',
        'replacement': r'log(t("live_engine.data.no_recent", symbol=symbol), level="ERROR")',
        'key': 'live_engine.data.no_recent'
    },
    
    # Stratégies
    {
        'pattern': r'log\(f"\[{symbol}\] 📊 Market detected: {(\w+)\.upper\(\)} — Strategy selected: {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.strategy.market_detected", symbol=symbol, condition=\1.upper(), strategy=\2), level="DEBUG")',
        'key': 'live_engine.strategy.market_detected'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 📊 Strategy manually selected: {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.strategy.manual_selected", symbol=symbol, strategy=\1), level="DEBUG")',
        'key': 'live_engine.strategy.manual_selected'
    },
    
    # Positions
    {
        'pattern': r'log\(f"\[{symbol}\] ✅ Position opened successfully", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.positions.opened_success", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.positions.opened_success'
    },
    
    # Scan
    {
        'pattern': r'log\("🔍 Lancement du scan indicateurs…", level="INFO"\)',
        'replacement': r'log(t("live_engine.scan.launch"), level="INFO")',
        'key': 'live_engine.scan.launch'
    },
    
    # Signaux
    {
        'pattern': r'log\(f"\[{symbol}\] 🎯 Signal detected: {(\w+)} \| Details: {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.signals.detected", symbol=symbol, signal=\1, details=\2), level="DEBUG")',
        'key': 'live_engine.signals.detected'
    },
]

def migrate_file(file_path):
    """Migre un fichier vers i18n"""
    print(f"🔄 Migration de {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    replacements_made = []
    
    # Ajouter l'import i18n si pas présent
    if 'from utils.i18n import t' not in content:
        # Trouver la ligne après les imports existants
        import_lines = []
        for line in content.split('\n'):
            if line.startswith('import ') or line.startswith('from '):
                import_lines.append(line)
        
        # Ajouter l'import i18n après le dernier import utils
        utils_imports = [line for line in import_lines if 'utils.' in line]
        if utils_imports:
            last_utils_import = utils_imports[-1]
            content = content.replace(last_utils_import, last_utils_import + '\nfrom utils.i18n import t')
            print("✅ Import i18n ajouté")
    
    # Appliquer les remplacements
    for repl in REPLACEMENTS:
        pattern = repl['pattern']
        replacement = repl['replacement']
        key = repl['key']
        
        matches = re.findall(pattern, content)
        if matches:
            content = re.sub(pattern, replacement, content)
            replacements_made.append({
                'key': key,
                'count': len(matches)
            })
            print(f"  ✅ {len(matches)}x {key}")
    
    # Sauvegarder si des changements ont été faits
    if content != original_content:
        # Créer une sauvegarde
        backup_path = f"{file_path}.backup"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"💾 Sauvegarde créée: {backup_path}")
        
        # Écrire le nouveau contenu
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Migration terminée: {len(replacements_made)} types de messages migrés")
        return True
    else:
        print("ℹ️ Aucun changement nécessaire")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python migrate_to_i18n.py <fichier.py>")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        sys.exit(1)
    
    print("🌍 Script de migration i18n")
    print("=" * 40)
    
    success = migrate_file(file_path)
    
    if success:
        print("\n🎉 Migration réussie !")
        print("📋 Actions recommandées:")
        print("  1. Tester le fichier migré")
        print("  2. Vérifier les logs")
        print("  3. Créer la version en.json")
        print("  4. Commit les changements")
    else:
        print("\n✨ Aucune migration nécessaire")

if __name__ == "__main__":
    main()