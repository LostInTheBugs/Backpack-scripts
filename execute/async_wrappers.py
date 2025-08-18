from execute.open_position_usdc import open_position as open_position_coroutine
from execute.close_position_percent import close_position_percent as sync_close_position
import asyncio
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

async def open_position_async(symbol: str, usdc_amount: float, direction: str, dry_run: bool = False):
    # Appel direct de la coroutine
    return await open_position_coroutine(symbol, usdc_amount, direction, dry_run)

async def close_position_percent_async(symbol: str, percent: float):
    # close_position_percent semble synchrone → ok d'utiliser run_in_executor
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_close_position, public_key, secret_key, symbol, percent)
