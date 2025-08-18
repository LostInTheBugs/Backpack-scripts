import requests
from datetime import datetime, timedelta, timezone
import time
import os
import asyncpg

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 21, startTime: int = None, endTime: int = None):
    if startTime is not None:
        print(f"[DEBUG] get_ohlcv called with startTime={startTime}")
        startTime_ms = int(startTime * 1000)
    else:
        startTime_ms = None

    if endTime is not None:
        endTime_ms = int(endTime * 1000)
    else:
        endTime_ms = None

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if startTime_ms is not None:
        params["startTime"] = startTime_ms
    if endTime_ms is not None:
        params["endTime"] = endTime_ms

    try:
        response = requests.get("https://api.backpack.exchange/api/v1/klines", params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[ERROR] get_ohlcv(): {e}")
        return None

def merge_symbols_with_config(auto_symbols: list) -> list:
    from config.settings import get_config
    config = get_config()
    """Fusionne auto-select avec include, puis enlève exclude."""
    include_list = [s.upper() for s in getattr(config.symbols, "include", [])]
    exclude_list = [s.upper() for s in getattr(config.symbols, "exclude", [])]

    # Normaliser les auto_symbols
    symbols_upper = [s.upper() for s in auto_symbols]

    # Ajouter tous les includes absents
    for s in include_list:
        if s not in symbols_upper:
            auto_symbols.append(s)

    # Retirer les excludes
    final_symbols = [s for s in auto_symbols if s.upper() not in exclude_list]

    return final_symbols

def format_table_name(symbol: str) -> str:
    parts = symbol.lower().split("_")
    return "ohlcv_" + "__".join(parts)

async def check_table_and_fresh_data(pool, symbol, max_age_seconds=600):
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
