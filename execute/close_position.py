# execute/close_position.py

import os
from bpx.account import Account, OrderTypeEnum
from bpx.public import Public

def get_step_size_decimals(market_info):
    step_size = market_info.get("filters", {}).get("quantity", {}).get("stepSize", "1")
    if '.' in step_size:
        return len(step_size.split(".")[1].rstrip("0"))
    return 0

def close_position(symbol, dry_run=False):
    print(f"[INFO] Fermeture de la position sur {symbol} (dry_run={dry_run})")

    if dry_run:
        print(f"[SIMULATION] Fermeture simulée de la position {symbol}")
        return True

    public_key = os.environ.get("bpx_bot_public_key")
    secret_key = os.environ.get("bpx_bot_secret_key")

    if not public_key or not secret_key:
        print("[ERROR] Clés API manquantes.")
        return False

    account = Account(public_key=public_key, secret_key=secret_key, window=5000)
    public = Public()

    markets = public.get_markets()
    market_info = next((m for m in markets if m.get("symbol") == symbol), None)
    if not market_info:
        print(f"[ERROR] Infos marché introuvables pour {symbol}")
        return False

    step_size_decimals = get_step_size_decimals(market_info)

    positions = account.get_open_positions()
    for position in positions:
        if position.get("symbol") != symbol:
            continue

        net_qty = float(position.get("netQuantity", "0"))
        if net_qty == 0:
            print(f"[INFO] Aucune position ouverte sur {symbol}")
            return False

        side = "Ask" if net_qty > 0 else "Bid"
        qty_to_close = round(abs(net_qty), step_size_decimals)

        print(f"🧾 Envoi ordre {side} MARKET pour fermer {qty_to_close} {symbol} (100%)")

        try:
            response = account.execute_order(
                symbol=symbol,
                side=side,
                order_type=OrderTypeEnum.MARKET,
                quantity=f"{qty_to_close:.{step_size_decimals}f}",
                reduce_only=True
            )
            print(f"[✅] Position fermée sur {symbol}")
            return True
        except Exception as e:
            print(f"[ERROR] Erreur lors de la fermeture : {e}")
            return False

    print(f"[INFO] Aucune position trouvée sur {symbol}")
    return False
