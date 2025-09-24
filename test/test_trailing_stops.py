#test_trailing_stops.py
"""
🧪 Script de test pour valider le système de trailing stops
À exécuter pour vérifier que la logique fonctionne correctement
"""

import asyncio
import sys
import os

# Ajouter le répertoire parent au path pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.live_engine import get_position_trailing_stop, should_close_position, TRAILING_STOPS
from config.settings import get_config

# Configuration de test
config = get_config()
MIN_PNL_FOR_TRAILING = config.trading.min_pnl_for_trailing
TRAILING_STOP_TRIGGER = config.trading.trailing_stop_trigger

async def test_trailing_stop_logic():
    """
    🧪 Test complet de la logique de trailing stop
    """
    print("🧪 === TEST TRAILING STOP LOGIC ===")
    print(f"Configuration: MIN_PNL = {MIN_PNL_FOR_TRAILING}%, TRIGGER = {TRAILING_STOP_TRIGGER}%")
    print()
    
    # Données de test
    symbol = "TEST_USDC_PERP"
    side = "long"
    entry_price = 100.0
    amount = 1.0
    
    # Scénarios de test
    test_scenarios = [
        {"mark_price": 100.5, "expected_pnl": 0.5, "should_activate": False},  # PnL < seuil
        {"mark_price": 101.0, "expected_pnl": 1.0, "should_activate": True},   # PnL = seuil
        {"mark_price": 102.0, "expected_pnl": 2.0, "should_activate": True},   # PnL > seuil
        {"mark_price": 101.5, "expected_pnl": 1.5, "should_activate": True},   # Retour en arrière
        {"mark_price": 103.0, "expected_pnl": 3.0, "should_activate": True},   # Nouveau max
        {"mark_price": 101.0, "expected_pnl": 1.0, "should_activate": True},   # Test fermeture
    ]
    
    print("🔍 SCÉNARIOS DE TEST:")
    for i, scenario in enumerate(test_scenarios, 1):
        mark_price = scenario["mark_price"]
        expected_pnl = scenario["expected_pnl"]
        should_activate = scenario["should_activate"]
        
        print(f"\n--- Test {i}: Mark Price = {mark_price} ---")
        
        # Appel de la fonction
        trailing_stop = await get_position_trailing_stop(
            symbol, side, entry_price, mark_price, amount
        )
        
        # Calcul du PnL réel
        actual_pnl = ((mark_price - entry_price) / entry_price) * 100
        
        # Vérifications
        print(f"  PnL calculé: {actual_pnl:.2f}% (attendu: {expected_pnl:.2f}%)")
        print(f"  Trailing stop: {trailing_stop}")
        print(f"  Devrait être activé: {should_activate}")
        
        if should_activate and trailing_stop is not None:
            print(f"  ✅ Trailing stop activé correctement")
            
            # Test de fermeture si le PnL baisse
            if actual_pnl <= trailing_stop:
                should_close = should_close_position(actual_pnl, trailing_stop, side, 1.0)
                print(f"  🚨 Position devrait être fermée: {should_close}")
            else:
                print(f"  ✅ Position safe (PnL {actual_pnl:.2f}% > Trailing {trailing_stop:.2f}%)")
                
        elif not should_activate and trailing_stop is None:
            print(f"  ⏳ Trailing stop pas encore activé (correct)")
        else:
            print(f"  ❌ Comportement inattendu!")
    
    print(f"\n🔍 État final du tracker:")
    for hash_key, data in TRAILING_STOPS.items():
        print(f"  Hash: {hash_key[:8]} | Active: {data['active']} | Max PnL: {data['max_pnl']:.2f}% | Trailing: {data.get('value', 'N/A')}")

async def test_config_values():
    """
    🔧 Test des valeurs de configuration
    """
    print("\n🔧 === CONFIGURATION TEST ===")
    print(f"MIN_PNL_FOR_TRAILING: {MIN_PNL_FOR_TRAILING}%")
    print(f"TRAILING_STOP_TRIGGER: {TRAILING_STOP_TRIGGER}%")
    print(f"Position amount: {config.trading.position_amount_usdc} USDC")
    print(f"Leverage: {config.trading.leverage}x")
    print(f"Max positions: {config.trading.max_positions}")

async def test_real_scenario():
    """
    🎯 Test avec vos données réelles
    """
    print("\n🎯 === TEST AVEC VOS DONNÉES RÉELLES ===")
    
    # Vos positions actuelles d'après les logs
    real_positions = [
        {"symbol": "PUMP_USDC_PERP", "side": "short", "entry": 0.005776, "mark": 0.005663, "expected_pnl": 1.95},
        {"symbol": "SUI_USDC_PERP", "side": "short", "entry": 3.6736, "mark": 3.38527, "expected_pnl": 7.85},
        {"symbol": "BTC_USDC_PERP", "side": "long", "entry": 112411, "mark": 112882, "expected_pnl": 0.42},
    ]
    
    for pos in real_positions:
        symbol = pos["symbol"]
        side = pos["side"]
        entry_price = pos["entry"]
        mark_price = pos["mark"]
        expected_pnl = pos["expected_pnl"]
        
        print(f"\n--- {symbol} ({side.upper()}) ---")
        
        trailing_stop = await get_position_trailing_stop(
            symbol, side, entry_price, mark_price, 1.0
        )
        
        # Calcul PnL
        if side == "long":
            actual_pnl = ((mark_price - entry_price) / entry_price) * 100
        else:
            actual_pnl = ((entry_price - mark_price) / entry_price) * 100
        
        print(f"  PnL calculé: {actual_pnl:.2f}% (attendu: {expected_pnl:.2f}%)")
        print(f"  Trailing stop: {trailing_stop}")
        
        if trailing_stop is not None:
            should_close = should_close_position(actual_pnl, trailing_stop, side, 1.0)
            print(f"  Fermeture nécessaire: {should_close}")
        else:
            print(f"  Pas encore activé (PnL {actual_pnl:.2f}% < {MIN_PNL_FOR_TRAILING}%)")

if __name__ == "__main__":
    async def main():
        await test_config_values()
        await test_trailing_stop_logic()
        await test_real_scenario()
        print("\n🎉 Tests terminés!")
    
    asyncio.run(main())
