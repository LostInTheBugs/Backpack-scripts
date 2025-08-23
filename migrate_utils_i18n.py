#!/usr/bin/env python3
"""
Migration des messages print() dans utils/ vers i18n
Usage: python migrate_utils_i18n.py
"""

import re
import sys
from pathlib import Path

# Nouveaux messages pour fr.json
NEW_FR_MESSAGES = '''
    "utils": {
        "logger": {
            "write_error": "[❌] Erreur écriture log : {error}"
        },
        "public": {
            "ohlcv_called": " get_ohlcv called with startTime={startTime}",
            "ohlcv_error": " get_ohlcv(): {error}",
            "table_not_exists": "❌ Table {table_name} n'existe pas.",
            "table_check_error": "❌ Erreur lors de la vérification de la table {table_name}: {error}"
        },
        "fetch_symbols": {
            "must_be_positive": "N doit être un entier positif",
            "must_be_integer": "N doit être un entier ou --no-limit",
            "usage": "Usage: python3 {script} N | --no-limit",
            "usage_n": "  N : nombre de symboles à récupérer",
            "usage_no_limit": "  --no-limit : récupérer tous les symboles",
            "symbols_saved": "✅ {count} symboles récupérés et sauvegardés dans {file}",
            "symbol_item": "  {i:2d}. {symbol}",
            "no_symbols": "❌ Aucun symbole récupéré"
        }
    }
'''

NEW_EN_MESSAGES = '''
    "utils": {
        "logger": {
            "write_error": "[❌] Log write error: {error}"
        },
        "public": {
            "ohlcv_called": " get_ohlcv called with startTime={startTime}",
            "ohlcv_error": " get_ohlcv(): {error}",
            "table_not_exists": "❌ Table {table_name} does not exist.",
            "table_check_error": "❌ Error checking table {table_name}: {error}"
        },
        "fetch_symbols": {
            "must_be_positive": "N must be a positive integer",
            "must_be_integer": "N must be an integer or --no-limit",
            "usage": "Usage: python3 {script} N | --no-limit",
            "usage_n": "  N: number of symbols to retrieve",
            "usage_no_limit": "  --no-limit: retrieve all symbols",
            "symbols_saved": "✅ {count} symbols retrieved and saved in {file}",
            "symbol_item": "  {i:2d}. {symbol}",
            "no_symbols": "❌ No symbols retrieved"
        }
    }
'''

# Patterns de remplacement pour chaque fichier
UTILS_REPLACEMENTS = {
    'utils/logger.py': [
        {
            'pattern': r'print\(f"\[❌\] Erreur écriture log : {(\w+)}"\)',
            'replacement': r'print(t("utils.logger.write_error", error=\1))',
            'add_import': True
        }
    ],
    'utils/public.py': [
        {
            'pattern': r'print\(f" get_ohlcv called with startTime={(\w+)}"\)',
            'replacement': r'print(t("utils.public.ohlcv_called", startTime=\1))',
            'add_import': True
        },
        {
            'pattern': r'print\(f" get_ohlcv\(\): {(\w+)}"\)',
            'replacement': r'print(t("utils.public.ohlcv_error", error=\1))',
            'add_import': True
        },
        {
            'pattern': r'print\(f"❌ Table {(\w+)} n\'existe pas\."\)',
            'replacement': r'print(t("utils.public.table_not_exists", table_name=\1))',
            'add_import': True
        },
        {
            'pattern': r'print\(f"❌ Erreur lors de la vérification de la table {(\w+)}: {(\w+)}"\)',
            'replacement': r'print(t("utils.public.table_check_error", table_name=\1, error=\2))',
            'add_import': True
        }
    ],
    'utils/fetch_top_n_volatility_volume.py': [
        {
            'pattern': r'print\("N doit être un entier positif"\)',
            'replacement': r'print(t("utils.fetch_symbols.must_be_positive"))',
            'add_import': True
        },
        {
            'pattern': r'print\("N doit être un entier ou --no-limit"\)',
            'replacement': r'print(t("utils.fetch_symbols.must_be_integer"))',
            'add_import': True
        },
        {
            'pattern': r'print\(f"Usage: python3 {sys\.argv\[0\]} N \| --no-limit"\)',
            'replacement': r'print(t("utils.fetch_symbols.usage", script=sys.argv[0]))',
            'add_import': True
        },
        {
            'pattern': r'print\("  N : nombre de symboles à récupérer"\)',
            'replacement': r'print(t("utils.fetch_symbols.usage_n"))',
            'add_import': True
        },
        {
            'pattern': r'print\("  --no-limit : récupérer tous les symboles"\)',
            'replacement': r'print(t("utils.fetch_symbols.usage_no_limit"))',
            'add_import': True
        },
        {
            'pattern': r'print\(f"✅ {len\((\w+)\)} symboles récupérés et sauvegardés dans {(\w+)}"\)',
            'replacement': r'print(t("utils.fetch_symbols.symbols_saved", count=len(\1), file=\2))',
            'add_import': True
        },
        {
            'pattern': r'print\(f"  {(\w+):2d}\. {(\w+)}"\)',
            'replacement': r'print(t("utils.fetch_symbols.symbol_item", i=\1, symbol=\2))',
            'add_import': True
        },
        {
            'pattern': r'print\("❌ Aucun symbole récupéré"\)',
            'replacement': r'print(t("utils.fetch_symbols.no_symbols"))',
            'add_import': True
        }
    ]
}

def migrate_utils_file(file_path):
    """Migre un fichier utils vers i18n"""
    print(f"🔄 Migration de {file_path}...")
    
    if not Path(file_path).exists():
        print(f"⚠️ Fichier {file_path} introuvable, ignoré")
        return False
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    replacements_made = []
    
    # Récupérer les patterns pour ce fichier
    patterns = UTILS_REPLACEMENTS.get(file_path, [])
    
    if not patterns:
        print(f"  ℹ️ Aucun pattern défini pour {file_path}")
        return False
    
    # Ajouter l'import i18n si nécessaire
    needs_import = any(p.get('add_import', False) for p in patterns)
    if needs_import and 'from utils.i18n import t' not in content:
        # Trouver un bon endroit pour ajouter l'import
        lines = content.split('\n')
        import_added = False
        
        for i, line in enumerate(lines):
            # Ajouter après les imports system et avant les imports locaux
            if (line.startswith('import ') or line.startswith('from ')) and 'utils.' not in line:
                continue
            else:
                lines.insert(i, 'from utils.i18n import t')
                content = '\n'.join(lines)
                import_added = True
                break
        
        if not import_added:
            # Si pas d'imports trouvés, ajouter au début après le shebang/docstring
            if content.startswith('#!/usr/bin/env python3'):
                lines = content.split('\n')
                lines.insert(1, 'from utils.i18n import t')
                content = '\n'.join(lines)
            else:
                content = 'from utils.i18n import t\n' + content
        
        print(f"  ✅ Import i18n ajouté")
    
    # Appliquer les remplacements
    for pattern_info in patterns:
        pattern = pattern_info['pattern']
        replacement = pattern_info['replacement']
        
        matches = re.findall(pattern, content, re.MULTILINE)
        if matches:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            replacements_made.append(len(matches))
            print(f"  ✅ {len(matches)} pattern(s) remplacé(s)")
    
    # Sauvegarder si des changements ont été faits
    if content != original_content:
        # Créer une sauvegarde
        backup_path = f"{file_path}.backup_utils"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"  💾 Sauvegarde: {backup_path}")
        
        # Écrire le nouveau contenu
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  ✅ Migration terminée: {sum(replacements_made)} remplacements")
        return True
    else:
        print(f"  ℹ️ Aucun changement nécessaire")
        return False

def update_locale_files():
    """Met à jour les fichiers de locale avec les nouveaux messages"""
    print("\n🌍 Mise à jour des fichiers de locale...")
    
    # Ajouter les nouveaux messages à fr.json
    fr_path = Path("locales/fr.json")
    if fr_path.exists():
        print("📝 Ajout des messages utils à fr.json")
        print("⚠️ ATTENTION: Ajoutez manuellement cette section à votre fr.json:")
        print(NEW_FR_MESSAGES)
    
    # Ajouter les nouveaux messages à en.json  
    en_path = Path("locales/en.json")
    if en_path.exists():
        print("📝 Ajout des messages utils à en.json")
        print("⚠️ ATTENTION: Ajoutez manuellement cette section à votre en.json:")
        print(NEW_EN_MESSAGES)

def main():
    print("🌍 Migration utils vers i18n")
    print("=" * 40)
    
    files_to_migrate = [
        'utils/logger.py',
        'utils/public.py', 
        'utils/fetch_top_n_volatility_volume.py'
    ]
    
    migrated_files = []
    
    for file_path in files_to_migrate:
        if migrate_utils_file(file_path):
            migrated_files.append(file_path)
    
    if migrated_files:
        print(f"\n🎉 Migration réussie pour {len(migrated_files)} fichier(s) !")
        print("📋 Fichiers migrés:")
        for f in migrated_files:
            print(f"  - {f}")
        
        update_locale_files()
        
        print("\n📋 Actions suivantes:")
        print("  1. Mettre à jour locales/fr.json et en.json manuellement")
        print("  2. Tester les fichiers migrés")
        print("  3. Commit les changements")
    else:
        print("\n✨ Aucune migration nécessaire")

if __name__ == "__main__":
    main()