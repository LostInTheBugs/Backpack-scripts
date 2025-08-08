import datetime
import pytz
import os
import psycopg2
import json
# Chemin du fichier de log
LOG_FILE_PATH = "logs/trading.log"

PG_DSN = os.environ.get("PG_DSN")

# S'assurer que le dossier logs/ existe
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

def get_now_paris():
    paris_tz = pytz.timezone("Europe/Paris")
    return datetime.datetime.now(paris_tz)

def format_log_entry(message):
    now = get_now_paris().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"[{now}] {message}"

def log(message, write_to_file=True, show_console=False):
    entry = format_log_entry(message)
    
    if show_console:
        print(entry)

    if write_to_file:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")

def utc_to_local(dt_utc):
    paris_tz = pytz.timezone("Europe/Paris")
    return dt_utc.astimezone(paris_tz)

def save_signal_to_db(symbol, timestamp, market_type, strategy, signal, price, rsi, trix, raw_data):
    try:
        conn = psycopg2.connect(PG_DSN)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO signals (timestamp, symbol, market_type, strategy, signal, price, rsi, trix, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            timestamp,
            symbol,
            market_type,
            strategy,
            signal,
            price,
            rsi,
            trix,
            json.dumps(raw_data)
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[❌] Erreur PostgreSQL : {e}")