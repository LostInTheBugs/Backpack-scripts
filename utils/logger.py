import datetime
import pytz
import os
import psycopg2
import json
from config.settings import get_logging_config

# Chemin du fichier de log
logging_config = get_logging_config()
LOG_FILE_PATH = logging_config.log_file_path
LOG_LEVEL = logging_config.log_level.upper()

# S'assurer que le dossier logs/ existe
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
}

def get_now_paris():
    paris_tz = pytz.timezone("Europe/Paris")
    return datetime.datetime.now(paris_tz)

def format_log_entry(level, message):
    now = get_now_paris().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"[{now}] [{level}] {message}"

def log(message, level="INFO", write_to_file=True, show_console=False):
    level = level.upper()
    current_level_value = LEVELS.get(LOG_LEVEL, 20)
    message_level_value = LEVELS.get(level, 20)

    if message_level_value < current_level_value:
        return  # Ne pas logger si niveau trop bas

    entry = format_log_entry(level, message)

    if show_console:
        print(entry)

    if write_to_file:
        try:
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception as e:
            print(f"[❌] Erreur écriture log : {e}")

def utc_to_local(dt_utc):
    paris_tz = pytz.timezone("Europe/Paris")
    return dt_utc.astimezone(paris_tz)

def save_signal_to_db(symbol, timestamp, market_type, strategy, signal, price, rsi, trix, raw_data):
    try:
        PG_DSN = os.environ.get("PG_DSN")
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
        log(f"Erreur PostgreSQL : {e}", level="ERROR")
