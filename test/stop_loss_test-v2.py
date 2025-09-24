#!/usr/bin/env python3
"""
Test pour vérifier que le stop-loss à -2% fonctionne IMMÉDIATEMENT (sans durée)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.live_engine import should_close_position

def test_stop_loss():
    print("Test du stop-loss fixe à -2% (SANS DURÉE MINIMALE)")
    print("=" * 60)
    
    # Vos positions actuelles qui DOIVENT se fermer
    real_positions = [
        {"symbol": "FARTCOIN", "pnl": -5.84, "should_close": True},
        {"symbol": "ASTER", "pnl": -5.72, "should_close": True},
        {"symbol": "AVNT", "pnl": -5.96, "should_close": True},
        {"symbol": "LINEA", "pnl": -5.87, "should_close": True},
        {"symbol": "ENA", "pnl": -3.67, "should_close": True},
        {"symbol": "ZORA", "pnl": -4.56, "should_close": True},
        {"symbol": "SOL", "pnl": -2.00, "should_close": True},  # Exactement -2%
        {"symbol": "DOGE", "pnl": -2.04, "should_close": True},
        {"symbol": "SUI", "pnl": 7.48, "should_close": False},  # Trailing stop gérera
        {"symbol": "PUMP", "pnl": 1.25, "should_close": False}, # Trailing stop gérera
    ]
    
    for pos in real_positions:
        symbol = pos["symbol"]
        pnl = pos["pnl"]
        expected = pos["should_close"]
        
        # Test avec durée très courte (0.01s)
        result = should_close_position(
            pnl_pct=pnl,
            trailing_stop=None,  # Pas de trailing stop
            side="long",
            duration_sec=0.01  # Très court
        )
        
        status = "✅" if result == expected else "❌ ERREUR"
        action = "FERMER" if result else "GARDER"
        print(f"{status} {symbol:<10} PnL: {pnl:+6.2f}% → {action} (attendu: {'FERMER' if expected else 'GARDER'})")
        
        if result != expected:
            print(f"   🚨 PROBLÈME: Cette position devrait {'se fermer' if expected else 'rester ouverte'}!")

if __name__ == "__main__":
    test_stop_loss()
