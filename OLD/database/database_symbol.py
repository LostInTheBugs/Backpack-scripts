import os
import sqlite3
from bpx.public import Public

# Création du dossier database s'il n'existe pas
os.makedirs("database", exist_ok=True)

DB_PATH = "symbols.db"

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            symbol TEXT PRIMARY KEY,
            last_price REAL,
            size_tick REAL
        )
    """)
    conn.commit()

def insert_or_update_symbol(conn, symbol, last_price, size_tick):
    conn.execute("""
        INSERT INTO symbols (symbol, last_price, size_tick)
        VALUES (?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            last_price=excluded.last_price,
            size_tick=excluded.size_tick
    """, (symbol, last_price, size_tick))
    conn.commit()

def main():
    public = Public()

    # Exemple : liste des symbols à traiter
    # Tu peux remplacer cette liste par la récupération dynamique si tu as une méthode
    symbols = [
        "BTC_USDC_PERP",
        "SOL_USDC_PERP",
        "ETH_USDC_PERP",
        # ajoute ici d'autres symbols que tu veux
    ]

    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    for symbol in symbols:
        ticker = public.get_ticker(symbol)
        if not isinstance(ticker, dict):
            print(f"Failed to retrieve ticker for {symbol}")
            continue

        last_price = float(ticker.get("lastPrice", 0))
        # Ici on récupère sizeTick si disponible, sinon None
        size_tick = ticker.get("sizeTick")
        if size_tick is not None:
            size_tick = float(size_tick)

        insert_or_update_symbol(conn, symbol, last_price, size_tick)
        print(f"Inserted/updated {symbol}: price={last_price}, sizeTick={size_tick}")

    conn.close()
    print("Database update done.")

if __name__ == "__main__":
    main()
