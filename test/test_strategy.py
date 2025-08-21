#!/usr/bin/env python3
"""
Script de test pour diagnostiquer pourquoi aucune position n'est ouverte
"""

import pandas as pd
import ta
import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
from config.settings import load_config

async def test_strategy_on_recent_data(symbol="BTC_USDC_PERP"):
    """Test la stratégie sur des données récentes"""
    config = load_config()
    pg_dsn = config.pg_dsn or os.environ.get("PG_DSN")
    
    pool = await asyncpg.create_pool(dsn=pg_dsn, min_size=1, max_size=2)
    
    # Format de table: ohlcv_{symbol avec __ au lieu de _}
    table_name = f"ohlcv_{symbol.lower().replace('_', '__')}"
    print(f"🔍 Recherche table: {table_name}")
    
    # Vérifie si la table existe
    try:
        count_query = f"SELECT COUNT(*) FROM {table_name}"
        total_rows = await pool.fetchval(count_query)
        print(f"✅ Table trouvée: {table_name} ({total_rows} rows total)")
    except Exception as e:
        print(f"❌ Erreur table {table_name}: {e}")
        await pool.close()
        return
    
    # Récupère les données des dernières 2 heures
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)
    
    query = f"""
    SELECT timestamp, open, high, low, close, volume 
    FROM {table_name} 
    WHERE timestamp BETWEEN $1 AND $2
    ORDER BY timestamp
    """
    
    rows = await pool.fetch(query, start_time, end_time)
    
    if not rows:
        print(f"❌ Pas de données pour {symbol}")
        return
        
    # Convertit en DataFrame
    df = pd.DataFrame([dict(row) for row in rows])
    df.set_index('timestamp', inplace=True)
    
    print(f"✅ Données chargées: {len(df)} points sur {symbol}")
    print(f"Prix actuel: {df['close'].iloc[-1]:.4f}")
    print(f"Variation 2h: {((df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100):.2f}%")
    
    # Calcule les indicateurs
    df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    df['MACD'] = ta.trend.MACD(close=df['close']).macd()
    df['MACD_signal'] = ta.trend.MACD(close=df['close']).macd_signal()
    df['EMA20'] = df['close'].ewm(span=20).mean()
    df['EMA50'] = df['close'].ewm(span=50).mean()
    
    # Affiche les valeurs actuelles
    current = df.iloc[-1]
    prev_5min = df.iloc[-300] if len(df) >= 300 else df.iloc[0]  # 5min = 300s
    
    print(f"\n📊 Indicateurs actuels:")
    print(f"RSI: {current['RSI']:.2f}")
    print(f"MACD: {current['MACD']:.6f}")
    print(f"MACD Signal: {current['MACD_signal']:.6f}")
    print(f"MACD > Signal: {current['MACD'] > current['MACD_signal']}")
    print(f"EMA20: {current['EMA20']:.4f}")
    print(f"EMA50: {current['EMA50']:.4f}")
    print(f"EMA20 > EMA50: {current['EMA20'] > current['EMA50']}")
    
    print(f"\n📈 Évolution 5min:")
    print(f"Prix: {prev_5min['close']:.4f} → {current['close']:.4f} ({((current['close']/prev_5min['close']-1)*100):+.2f}%)")
    print(f"RSI: {prev_5min['RSI']:.2f} → {current['RSI']:.2f} ({current['RSI']-prev_5min['RSI']:+.2f})")
    
    # Test conditions simples
    print(f"\n🎯 Conditions de signal:")
    
    # BUY conditions
    buy_rsi = current['RSI'] < 35
    buy_macd = current['MACD'] > current['MACD_signal'] and prev_5min['MACD'] <= prev_5min['MACD_signal']
    buy_trend = current['EMA20'] > current['EMA50']
    
    print(f"BUY - RSI < 35: {buy_rsi} (RSI={current['RSI']:.2f})")
    print(f"BUY - MACD Cross: {buy_macd}")
    print(f"BUY - Trend Up: {buy_trend}")
    print(f"BUY Signal: {buy_rsi and (buy_macd or buy_trend)}")
    
    # SELL conditions  
    sell_rsi = current['RSI'] > 65
    sell_macd = current['MACD'] < current['MACD_signal'] and prev_5min['MACD'] >= prev_5min['MACD_signal']
    sell_trend = current['EMA20'] < current['EMA50']
    
    print(f"SELL - RSI > 65: {sell_rsi} (RSI={current['RSI']:.2f})")
    print(f"SELL - MACD Cross: {sell_macd}")
    print(f"SELL - Trend Down: {sell_trend}")
    print(f"SELL Signal: {sell_rsi and (sell_macd or sell_trend)}")
    
    # Teste sur les 30 dernières minutes
    print(f"\n🔍 Signaux sur les 30 dernières minutes:")
    recent_df = df.iloc[-1800:] if len(df) >= 1800 else df  # 30min = 1800s
    
    signals = []
    for i in range(50, len(recent_df)):  # Skip premiers points sans indicateurs
        row = recent_df.iloc[i]
        prev_row = recent_df.iloc[i-1]
        
        if (row['RSI'] < 35 and 
            row['MACD'] > row['MACD_signal'] and 
            prev_row['MACD'] <= prev_row['MACD_signal']):
            signals.append(('BUY', row.name, row['close'], row['RSI']))
            
        elif (row['RSI'] > 65 and 
              row['MACD'] < row['MACD_signal'] and 
              prev_row['MACD'] >= prev_row['MACD_signal']):
            signals.append(('SELL', row.name, row['close'], row['RSI']))
    
    if signals:
        print(f"Trouvé {len(signals)} signaux:")
        for signal_type, timestamp, price, rsi in signals[-5:]:  # 5 derniers
            print(f"  {signal_type} à {timestamp} - Prix: {price:.4f}, RSI: {rsi:.2f}")
    else:
        print("❌ Aucun signal détecté sur la période")
        
    await pool.close()

if __name__ == "__main__":
    asyncio.run(test_strategy_on_recent_data("BTC_USDC_PERP"))