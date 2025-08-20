#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from config.settings import load_config

async def debug_table_names():
    """Debug pour comprendre le mapping des noms de tables"""
    
    config = load_config()
    pg_dsn = config.pg_dsn or os.environ.get('PG_DSN')
    
    pool = await asyncpg.create_pool(dsn=pg_dsn)
    
    print("=== DIAGNOSTIC DES TABLES ===")
    
    # 1. Lister toutes les tables OHLCV
    print("1. Tables OHLCV disponibles:")
    tables = await pool.fetch("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'ohlcv%';")
    for table in tables:
        print(f"   - {table['table_name']}")
    
    print()
    
    # 2. Test de conversion de noms
    test_symbols = ['BTC_USDC_PERP', 'SOL_USDC_PERP', 'ETH_USDC_PERP']
    
    print("2. Test de conversion de noms:")
    for symbol in test_symbols:
        # Conversion probable dans votre code
        table_name_1 = f"ohlcv_{symbol.lower().replace('_', '__')}"
        table_name_2 = f"ohlcv_{symbol.lower()}"
        table_name_3 = symbol.lower()
        
        print(f"   Symbol: {symbol}")
        print(f"     -> Possible table 1: {table_name_1}")
        print(f"     -> Possible table 2: {table_name_2}")
        print(f"     -> Possible table 3: {table_name_3}")
        
        # Test si ces tables existent
        for i, table_name in enumerate([table_name_1, table_name_2, table_name_3], 1):
            try:
                result = await pool.fetchval(f"SELECT COUNT(*) FROM {table_name} LIMIT 1;")
                print(f"     ✅ Table {i} EXISTS with {result} rows")
                
                # Test données récentes
                recent = await pool.fetchval(f"""
                    SELECT COUNT(*) FROM {table_name} 
                    WHERE timestamp > NOW() - INTERVAL '10 minutes';
                """)
                print(f"     📊 Recent data (10min): {recent} rows")
                
            except Exception as e:
                print(f"     ❌ Table {i} DOES NOT EXIST: {str(e)[:50]}...")
        
        print()
    
    # 3. Test de la fonction check_table_and_fresh_data
    print("3. Test de check_table_and_fresh_data:")
    try:
        from utils.public import check_table_and_fresh_data
        
        for symbol in test_symbols:
            result = await check_table_and_fresh_data(pool, symbol, max_age_seconds=600)
            print(f"   {symbol}: {result}")
    except Exception as e:
        print(f"   ❌ Erreur: {e}")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(debug_table_names())