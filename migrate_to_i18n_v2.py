#!/usr/bin/env python3
"""
Script de migration i18n v2 - Messages restants dans live/live_engine.py
Usage: python migrate_to_i18n_v2.py live/live_engine.py
"""

import re
import sys
from pathlib import Path

# Nouveaux patterns pour les messages restants
ADDITIONAL_REPLACEMENTS = [
    # Messages RSI/MACD non encore migrés
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
        'pattern': r'log\(f"\[{symbol}\] 🔄 RSI calculé localement: {(\w+)\.iloc\[-1\]:.2f}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.indicators.rsi_calculated", symbol=symbol, rsi=\1.iloc[-1]), level="DEBUG")',
        'key': 'live_engine.indicators.rsi_calculated'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ Impossible de calculer RSI localement, valeur neutre: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.indicators.rsi_failed", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.indicators.rsi_failed'
    },
    
    # Messages de données
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ No 1s data retrieved from local database", level="ERROR"\)',
        'replacement': r'log(t("live_engine.data.no_1s_data", symbol=symbol), level="ERROR")',
        'key': 'live_engine.data.no_1s_data'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] DataFrame validated - shape: {df\.shape}, columns: {list\(df\.columns\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.data.dataframe_validated", symbol=symbol, shape=df.shape, columns=list(df.columns)), level="DEBUG")',
        'key': 'live_engine.data.dataframe_validated'
    },
    
    # Messages de stratégie/debug
    {
        'pattern': r'log\(f"\[{symbol}\] About to call strategy: {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.strategy.about_to_call", symbol=symbol, strategy=\1), level="DEBUG")',
        'key': 'live_engine.strategy.about_to_call'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 🔄 Calling async strategy function", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.strategy.calling_async", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.strategy.calling_async'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] Strategy returned: {type\((\w+)\)} - {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.strategy.returned", symbol=symbol, type=type(\1), result=\2), level="DEBUG")',
        'key': 'live_engine.strategy.returned'
    },
    
    # Messages d'erreur
    {
        'pattern': r'log\(f"\[{symbol}\] 💥 Error: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.generic", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.errors.generic'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Error calling strategy function: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.strategy.error", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.strategy.error'
    },
    
    # Messages de positions
    {
        'pattern': r'log\(f"\[{symbol}\] ✅ Position closed successfully", level="INFO"\)',
        'replacement': r'log(t("live_engine.positions.closed_success", symbol=symbol), level="INFO")',
        'key': 'live_engine.positions.closed_success'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Error opening position: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.positions.open_error", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.positions.open_error'
    },
    
    # Messages debug restants
    {
        'pattern': r'log\(f"\[{symbol}\] ensure_indicators returned type: {type\((\w+)\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.ensure_indicators_type", symbol=symbol, type=type(\1)), level="DEBUG")',
        'key': 'live_engine.debug.ensure_indicators_type'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] Is coroutine\? {asyncio\.iscoroutine\((\w+)\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.is_coroutine", symbol=symbol, is_coroutine=asyncio.iscoroutine(\1)), level="DEBUG")',
        'key': 'live_engine.debug.is_coroutine'
    },
    
    # Messages simples sans paramètres
    {
        'pattern': r'log\(f"🔍 Lancement du scan indicateurs et trading en parallèle…", level="INFO"\)',
        'replacement': r'log(t("live_engine.scan.launch_trade"), level="INFO")',
        'key': 'live_engine.scan.launch_trade'
    },
    {
        'pattern': r'log\(f"{symbol} ❌ No actionable signal detected: {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.signals.no_actionable", symbol=symbol, signal=\1), level="DEBUG")',
        'key': 'live_engine.signals.no_actionable'
    },
]

def migrate_additional_patterns(file_path):
    """Migre les patterns additionnels vers i18n"""
    print(f"🔄 Migration v2 de {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    replacements_made = []
    
    # Appliquer les nouveaux remplacements
    for repl in ADDITIONAL_REPLACEMENTS:
        pattern = repl['pattern']
        replacement = repl['replacement']
        key = repl['key']
        
        matches = re.findall(pattern, content, re.MULTILINE)
        if matches:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            replacements_made.append({
                'key': key,
                'count': len(matches)
            })
            print(f"  ✅ {len(matches)}x {key}")
    
    # Messages simples restants (patterns flexibles)
    simple_patterns = [
        (r'log\(f"✅ OK: {(\w+)}", level="DEBUG"\)', r'log(t("live_engine.scan.ok_symbols", symbols=\1), level="DEBUG")'),
        (r'log\(f"❌ KO: {(\w+)}", level="DEBUG"\)', r'log(t("live_engine.scan.ko_symbols", symbols=\1), level="DEBUG")'),
    ]
    
    for pattern, replacement in simple_patterns:
        matches = re.findall(pattern, content)
        if matches:
            content = re.sub(pattern, replacement, content)
            print(f"  ✅ {len(matches)}x pattern simple")
    
    # Sauvegarder si des changements ont été faits
    if content != original_content:
        # Créer une sauvegarde v2
        backup_path = f"{file_path}.backup_v2"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"💾 Sauvegarde v2 créée: {backup_path}")
        
        # Écrire le nouveau contenu
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Migration v2 terminée: {len(replacements_made)} nouveaux types migrés")
        
        # Compter les messages restants
        remaining_logs = len(re.findall(r'log\(f"', content))
        print(f"📊 Messages log restants: {remaining_logs}")
        
        return True
    else:
        print("ℹ️ Aucun nouveau changement nécessaire")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python migrate_to_i18n_v2.py <fichier.py>")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        sys.exit(1)
    
    print("🌍 Script de migration i18n v2")
    print("=" * 40)
    
    success = migrate_additional_patterns(file_path)
    
    if success:
        print("\n🎉 Migration v2 réussie !")
        print("📋 Prochaines actions:")
        print("  1. Tester le système")
        print("  2. Vérifier les nouveaux messages")
        print("  3. Continuer avec d'autres fichiers")
        print("  4. Créer en.json complet")
    else:
        print("\n✨ Déjà à jour")

if __name__ == "__main__":
    main()