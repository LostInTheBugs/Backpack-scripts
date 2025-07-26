import requests
from datetime import datetime
import requests
import time
import numpy as np
import pandas as pd

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 21, startTime: int = None):
    base_url = "https://api.backpack.exchange/api/v1/klines"
    
    if startTime is None:
        # Par défaut : récupérer les dernières `limit` bougies 1m, donc startTime = now - limit*60s
        startTime = int(time.time()) - limit * 60
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "startTime": startTime
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as e:
        print(f"[ERROR] get_ohlcv(): {e}")
        return None

def format_table_name(symbol: str) -> str:
    parts = symbol.lower().split("_")
    return "ohlcv_" + "__".join(parts)

async def check_table_and_fresh_data(pool, symbol, max_age_seconds=60):
    table_name = format_table_name(symbol)
    async with pool.acquire() as conn:
        try:
            recent_rows = await conn.fetch(
                f"""
                SELECT * FROM {table_name}
                WHERE timestamp >= $1
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds),
            )
            return bool(recent_rows)
        except asyncpg.exceptions.UndefinedTableError:
            print(f"❌ Table {table_name} n'existe pas.")
            return False
        except Exception as e:
            print(f"❌ Erreur lors de la vérification de la table {table_name}: {e}")
            return False
        
async def get_last_timestamp(pool, symbol):
    table_name = format_table_name(symbol)
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                f"SELECT timestamp FROM {table_name} ORDER BY timestamp DESC LIMIT 1"
            )
            return row["timestamp"] if row else None
        except asyncpg.exceptions.UndefinedTableError:
            return None        
        

def load_symbols_from_file(filepath: str = "symbol.lst") -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]