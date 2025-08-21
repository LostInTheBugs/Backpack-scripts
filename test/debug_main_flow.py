#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from config.settings import load_config
from utils.fetch_top_n_volatility_volume import fetch_top_n_volatility_volume
from utils.public import check_table_and_fresh_data

async def debug_main_flow():
    """Debug complet du flux principal comme dans main.py"""
    
    print("=== DEBUG DU FLUX PRINCIPAL ===")
    
    # 1. Charger la config comme dans main.py
    config = load_config()
    print(f"✅ Config loaded")
    
    # 2. Récupérer auto_symbols comme dans main.py
    try:
        auto_symbols_result = fetch_top_n_volatility_volume(n=getattr(config.strategy, "auto_select_top_n", 10))
        auto_symbols = auto_symbols_result if auto_symbols_result is not None else []
        print(f"✅ Auto symbols récupérés: {auto_symbols}")
    except Exception as e:
        print(f"❌ Erreur auto_symbols: {e}")
        auto_symbols = []
    
    # 3. Include/exclude comme dans main.py
    include_symbols = getattr(config.strategy, 'include', []) or []
    exclude_symbols = getattr(config.strategy, 'exclude', []) or []
    
    print(f"📋 Include symbols: {include_symbols}")
    print(f"🚫 Exclude symbols: {exclude_symbols}")
    
    # 4. Fusion comme dans main.py
    all_symbols = list(set(auto_symbols + include_symbols))
    final_symbols = [s for s in all_symbols if s not in exclude_symbols]
    
    print(f"🔄 All symbols (after merge): {all_symbols}")
    print(f"🎯 Final symbols (after exclude): {final_symbols}")
    
    # 5. Créer symbols_container comme dans main.py
    symbols_container = {'list': final_symbols}
    print(f"📦 Symbols container: {symbols_container}")
    
    # 6. Connexion DB comme dans main.py
    db_config = config.database
    pg_dsn = config.pg_dsn or os.environ.get("PG_DSN")
    
    pool = await asyncpg.create_pool(
        dsn=pg_dsn,
        min_size=db_config.pool_min_size,
        max_size=db_config.pool_max_size
    )
    print(f"✅ Pool créé")
    
    # 7. Test check_table_and_fresh_data pour chaque symbole
    print(f"\n🔍 Test individual symbols:")
    active_symbols = []
    ignored_symbols = []
    
    for symbol in final_symbols[:5]:  # Test seulement les 5 premiers
        try:
            result = await check_table_and_fresh_data(pool, symbol, max_age_seconds=config.database.max_age_seconds)
            print(f"   {symbol}: {result}")
            
            if result:
                active_symbols.append(symbol)
            else:
                ignored_symbols.append(symbol)
                
        except Exception as e:
            print(f"   {symbol}: ERROR - {e}")
            ignored_symbols.append(symbol)
    
    print(f"\n📊 RÉSULTATS:")
    print(f"   Active symbols ({len(active_symbols)}): {active_symbols}")
    print(f"   Ignored symbols ({len(ignored_symbols)}): {ignored_symbols}")
    print(f"   Config max_age_seconds: {config.database.max_age_seconds}")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(debug_main_flow())