import datetime
import pytz
import os

# Chemin du fichier de log
LOG_FILE_PATH = "logs/trading.log"

# S'assurer que le dossier logs/ existe
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

def get_now_paris():
    paris_tz = pytz.timezone("Europe/Paris")
    return datetime.datetime.now(paris_tz)

def format_log_entry(message):
    now = get_now_paris().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"[{now}] {message}"

def log(message, write_to_file=True):
    entry = format_log_entry(message)
    print(entry)

    if write_to_file:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")

def utc_to_local(dt_utc):
    paris_tz = pytz.timezone("Europe/Paris")
    return dt_utc.astimezone(paris_tz)
