# read/open_position_utils.py

from bpx.account import Account
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

def get_open_positions():
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    positions = account.get_open_positions()

    if not isinstance(positions, list):
        raise ValueError(f"Failed to retrieve open positions: {positions}")
    
    return positions

def has_open_position(symbol: str) -> bool:
    positions = get_open_positions()
    for p in positions:
        if p.get("symbol") == symbol and float(p.get("netQuantity", 0)) != 0:
            return True
    return False

def get_position_pnl(symbol: str) -> float:
    positions = get_open_positions()
    for p in positions:
        if p.get("symbol") == symbol:
            return float(p.get("pnlUnrealized", 0))
    return 0.0
