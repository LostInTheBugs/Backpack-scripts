import os
import requests

def close_position(symbol, dry_run=False):
    print(f"[INFO] Fermeture de la position sur {symbol} (dry_run={dry_run})")

    if dry_run:
        print(f"[SIMULATION] Fermeture simulée de la position {symbol}")
        return True

    base_url = "https://api.backpack.exchange/api/v1"
    api_key = os.getenv("bpx_bot_public_key")
    api_secret = os.getenv("bpx_bot_secret_key")

    if not api_key or not api_secret:
        print("[ERROR] Clés API manquantes.")
        return False

    headers = {
        "X-BPX-API-KEY": api_key,
        "X-BPX-API-SECRET": api_secret,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{base_url}/orders/close-position",
            headers=headers,
            json={"symbol": symbol}
        )
        response.raise_for_status()
        print(f"[✅] Position fermée sur {symbol}")
        return True
    except Exception as e:
        print(f"[ERROR] Échec fermeture position : {e}")
        return False
