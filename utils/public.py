import requests
from datetime import datetime, timedelta, timezone
import time
import os
import asyncpg

def get_ohlcv(symbol: str, interval: str = "1m", limit: int = 1000, startTime: int = None, endTime: int = None):
    # Définir la limite maximale de jours entre startTime et endTime
    max_days = 200
    max_ms = max_days * 24 * 3600 * 1000  # Convertir les jours en millisecondes

    # Si startTime est fourni, calculer endTime
    if startTime:
        if not endTime:
            endTime = startTime + max_ms
        elif endTime - startTime > max_ms:
            print(f"[ERROR] La plage de temps entre {startTime} et {endTime} dépasse la limite de {max_days} jours.")
            return None
    else:
        # Si startTime n'est pas fourni, définir une valeur par défaut (par exemple, 30 jours avant maintenant)
        endTime = int(time.time() * 1000)
        startTime = endTime - max_ms

    # Construire l'URL de la requête
    url = f"https://api.backpack.exchange/api/v1/klines?symbol={symbol}&interval={interval}&startTime={startTime}&endTime={endTime}&limit={limit}"

    # Effectuer la requête et gérer les erreurs
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[ERROR] get_ohlcv() : {e}")
        return None


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
