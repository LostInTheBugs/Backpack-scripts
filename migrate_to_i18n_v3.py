#!/usr/bin/env python3
"""
Script de migration i18n v3 - Finalisation des 37 messages restants
Usage: python migrate_to_i18n_v3.py live/live_engine.py
"""

import re
import sys
from pathlib import Path

# Patterns pour les 37 messages restants
FINAL_REPLACEMENTS = [
    # Trailing stop (5 messages)
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Error calculating trailing stop: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.trailing_stop.error", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.trailing_stop.error'
    },
    {
        'pattern': r'log\(f"Fixed stop loss triggered: PnL {(\w+):.2f}% <= Stop Loss {(\w+):.2f}%", level="INFO"\)',
        'replacement': r'log(t("live_engine.stop_loss.fixed_triggered", pnl=\1, stop_loss=\2), level="INFO")',
        'key': 'live_engine.stop_loss.fixed_triggered'
    },
    {
        'pattern': r'log\(f"Trailing stop triggered: PnL {(\w+):.2f}% <= Trailing {(\w+):.2f}%", level="INFO"\)',
        'replacement': r'log(t("live_engine.trailing_stop.triggered", pnl=\1, trailing=\2), level="INFO")',
        'key': 'live_engine.trailing_stop.triggered'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 🎯 Closing position due to trailing stop trigger", level="INFO"\)',
        'replacement': r'log(t("live_engine.trailing_stop.closing", symbol=symbol), level="INFO")',
        'key': 'live_engine.trailing_stop.closing'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 🧹 Trailing stop cleaned from memory", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.trailing_stop.cleaned", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.trailing_stop.cleaned'
    },
    
    # Messages d'erreur (8 messages)
    {
        'pattern': r'log\(f"Error checking fixed stop loss: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.stop_loss.check_error", error=\1), level="ERROR")',
        'key': 'live_engine.stop_loss.check_error'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Indicators calculation failed", level="ERROR"\)',
        'replacement': r'log(t("live_engine.indicators.calculation_failed", symbol=symbol), level="ERROR")',
        'key': 'live_engine.indicators.calculation_failed'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Expected DataFrame but got {type\((\w+)\)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.data.dataframe_error", symbol=symbol, type=type(\1)), level="ERROR")',
        'key': 'live_engine.data.dataframe_error'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Error closing position: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.positions.close_error", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.positions.close_error'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Error in handle_existing_position: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.position_handling", symbol=symbol, error=\1), level="ERROR")',
        'key': 'live_engine.errors.position_handling'
    },
    {
        'pattern': r'log\(f"⚠️ Error checking position limit: {(\w+)}", level="WARNING"\)',
        'replacement': r'log(t("live_engine.errors.position_limit", error=\1), level="WARNING")',
        'key': 'live_engine.errors.position_limit'
    },
    {
        'pattern': r'log\(f"⚠️ Error getting position stats: {(\w+)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.position_stats", error=\1), level="ERROR")',
        'key': 'live_engine.errors.position_stats'
    },
    
    # Messages de positions (7 messages)
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ No valid open position found", level="WARNING"\)',
        'replacement': r'log(t("live_engine.positions.no_valid_found", symbol=symbol), level="WARNING")',
        'key': 'live_engine.positions.no_valid_found'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ Unexpected return type from get_real_pnl: {type\((\w+)\)}", level="WARNING"\)',
        'replacement': r'log(t("live_engine.positions.unexpected_pnl_type", symbol=symbol, type=type(\1)), level="WARNING")',
        'key': 'live_engine.positions.unexpected_pnl_type'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ Maximum positions limit \({trading_config\.max_positions}\) reached - skipping", level="WARNING"\)',
        'replacement': r'log(t("live_engine.positions.limit_reached", symbol=symbol, max=trading_config.max_positions), level="WARNING")',
        'key': 'live_engine.positions.limit_reached'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 🧪 DRY-RUN: Simulated {(\w+)\.upper\(\)} position opening", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.positions.opening_dry", symbol=symbol, direction=\1.upper()), level="DEBUG")',
        'key': 'live_engine.positions.opening_dry'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ✅ REAL position opening: {(\w+)\.upper\(\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.positions.opening_real", symbol=symbol, direction=\1.upper()), level="DEBUG")',
        'key': 'live_engine.positions.opening_real'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ❌ Neither --real-run nor --dry-run specified: no action", level="ERROR"\)',
        'replacement': r'log(t("live_engine.positions.neither_run_mode", symbol=symbol), level="ERROR")',
        'key': 'live_engine.positions.neither_run_mode'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 🧪 DRY-RUN: Would close position due to trailing stop", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.positions.dry_run_close", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.positions.dry_run_close'
    },
    
    # Messages debug/info détaillés (10 messages)
    {
        'pattern': r'log\(f"\[{symbol}\] Function type: {type\((\w+)\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.function_type", symbol=symbol, type=type(\1)), level="DEBUG")',
        'key': 'live_engine.debug.function_type'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] Is coroutine function\? {inspect\.iscoroutinefunction\((\w+)\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.is_coroutine_function", symbol=symbol, is_coroutine=inspect.iscoroutinefunction(\1)), level="DEBUG")',
        'key': 'live_engine.debug.is_coroutine_function'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] DataFrame type before call: {type\((\w+)\)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.dataframe_before_call", symbol=symbol, type=type(\1)), level="DEBUG")',
        'key': 'live_engine.debug.dataframe_before_call'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] DataFrame shape: {(\w+)\.shape}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.dataframe_shape", symbol=symbol, shape=\1.shape), level="DEBUG")',
        'key': 'live_engine.debug.dataframe_shape'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] 🔄 Calling sync strategy function", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.strategy.calling_sync", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.strategy.calling_sync'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] CLOSE CHECK: PnL={(\w+):.2f}%, Trailing={(\w+)}, Duration={(\w+)}s, ShouldClose={(\w+)}", level="INFO"\)',
        'replacement': r'log(t("live_engine.debug.close_check", symbol=symbol, pnl=\1, trailing=\2, duration=\3, should_close=\4), level="INFO")',
        'key': 'live_engine.debug.close_check'
    },
    
    # Messages indicateurs (2 messages)
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ Indicateurs manquants: {(\w+)} — signal ignoré\.", level="WARNING"\)',
        'replacement': r'log(t("live_engine.indicators.missing", symbol=symbol, missing=\1), level="WARNING")',
        'key': 'live_engine.indicators.missing'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ NaN détecté dans {(\w+)} — signal ignoré\.", level="WARNING"\)',
        'replacement': r'log(t("live_engine.indicators.nan_detected", symbol=symbol, column=\1), level="WARNING")',
        'key': 'live_engine.indicators.nan_detected'
    },
    
    # Messages divers (5 messages)
    {
        'pattern': r'log\(f"⚠️ Unexpected result in scan_all_symbols: {(\w+)}", level="WARNING"\)',
        'replacement': r'log(t("live_engine.scan.unexpected_result", result=\1), level="WARNING")',
        'key': 'live_engine.scan.unexpected_result'
    },
    {
        'pattern': r'log\(f"📊 Résumé: {len\((\w+)\)} OK / {len\((\w+)\)} KO sur {len\((\w+)\)} paires\.", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.scan.summary", ok_count=len(\1), ko_count=len(\2), total=len(\3)), level="DEBUG")',
        'key': 'live_engine.scan.summary'
    },
    {
        'pattern': r'log\(f"{symbol} 🚨 Try open position: {(\w+)}", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.signals.try_open", symbol=symbol, signal=\1), level="DEBUG")',
        'key': 'live_engine.signals.try_open'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] ⚠️ DataFrame is empty after indicators calculation", level="WARNING"\)',
        'replacement': r'log(t("live_engine.data.dataframe_empty", symbol=symbol), level="WARNING")',
        'key': 'live_engine.data.dataframe_empty'
    },
    {
        'pattern': r'log\(f"\[{symbol}\] Awaiting coroutine from ensure_indicators\.\.\.", level="DEBUG"\)',
        'replacement': r'log(t("live_engine.debug.awaiting_coroutine", symbol=symbol), level="DEBUG")',
        'key': 'live_engine.debug.awaiting_coroutine'
    },
]

# Messages debug avec info détaillée (patterns plus complexes)
ERROR_INFO_PATTERNS = [
    {
        'pattern': r'log\(f"\[{symbol}\] DataFrame info at time of error:", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.dataframe_info", symbol=symbol), level="ERROR")',
        'key': 'live_engine.errors.dataframe_info'
    },
    {
        'pattern': r'log\(f"\[{symbol}\]   - Type: {type\((\w+)\)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.dataframe_type", symbol=symbol, type=type(\1)), level="ERROR")',
        'key': 'live_engine.errors.dataframe_type'
    },
    {
        'pattern': r'log\(f"\[{symbol}\]   - Is coroutine\? {asyncio\.iscoroutine\((\w+)\)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.dataframe_is_coroutine", symbol=symbol, is_coroutine=asyncio.iscoroutine(\1)), level="ERROR")',
        'key': 'live_engine.errors.dataframe_is_coroutine'
    },
    {
        'pattern': r'log\(f"\[{symbol}\]   - Shape: {(\w+)\.shape}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.dataframe_shape_error", symbol=symbol, shape=\1.shape), level="ERROR")',
        'key': 'live_engine.errors.dataframe_shape_error'
    },
    {
        'pattern': r'log\(f"\[{symbol}\]   - Columns: {list\((\w+)\.columns\)}", level="ERROR"\)',
        'replacement': r'log(t("live_engine.errors.dataframe_columns_error", symbol=symbol, columns=list(\1.columns)), level="ERROR")',
        'key': 'live_engine.errors.dataframe_columns_error'
    },
]

def migrate_final_patterns(file_path):
    """Migration finale - tous les 37 messages restants"""
    print(f"🎯 Migration finale de {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    replacements_made = []
    
    # Appliquer tous les remplacements finaux
    all_patterns = FINAL_REPLACEMENTS + ERROR_INFO_PATTERNS
    
    for repl in all_patterns:
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
    
    # Sauvegarder si des changements ont été faits
    if content != original_content:
        # Créer une sauvegarde v3
        backup_path = f"{file_path}.backup_v3"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"💾 Sauvegarde v3 créée: {backup_path}")
        
        # Écrire le nouveau contenu
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Migration finale terminée: {len(replacements_made)} types migrés")
        
        # Compter les messages restants
        remaining_logs = len(re.findall(r'log\(f"', content))
        print(f"🎉 Messages log f-string restants: {remaining_logs}")
        
        return True, len(replacements_made)
    else:
        print("ℹ️ Aucun changement nécessaire")
        return False, 0

def main():
    if len(sys.argv) != 2:
        print("Usage: python migrate_to_i18n_v3.py <fichier.py>")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"❌ Fichier non trouvé: {file_path}")
        sys.exit(1)
    
    print("🌍 Script de migration i18n v3 - FINALISATION")
    print("=" * 50)
    
    success, migrated_count = migrate_final_patterns(file_path)
    
    if success:
        print(f"\n🎉 MIGRATION COMPLÈTE RÉUSSIE !")
        print(f"📊 Total de types migrés: {migrated_count}")
        print(f"🎯 Le fichier live/live_engine.py est maintenant majoritairement i18n !")
        print("\n📋 Prochaines actions:")
        print("  1. Tester le système complet")
        print("  2. Créer en.json avec toutes les clés")
        print("  3. Migrer d'autres fichiers (main.py, etc.)")
        print("  4. Commit cette migration majeure")
    else:
        print("\n✨ Migration déjà complète")

if __name__ == "__main__":
    main()