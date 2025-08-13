from execute.open_position_usdc import open_position as sync_open_position
from execute.close_position_percent import close_position_percent as sync_close_position
import asyncio
import os

public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")

async def open_position_async(symbol: str, usdc_amount: float, direction: str, dry_run: bool = False):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_open_position, symbol, usdc_amount, direction, dry_run)

async def close_position_percent_async(symbol: str, percent: float):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_close_position, public_key, secret_key, symbol, percent)
