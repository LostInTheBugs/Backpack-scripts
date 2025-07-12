import asyncio
import json
import websockets
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from execute.open_position_usdc import open_position
from bpx.account import Account

account = Account(
    public_key=os.environ.get("bpx_bot_public_key"),
    secret_key=os.environ.get("bpx_bot_secret_key"),
)

orderbook = {"bids": {}, "asks": {}}
has_position = False  # verrou local

async def websocket_orderbook(symbol):
    global orderbook
    url = "wss://ws.backpack.exchange"
    async with websockets.connect(url) as ws:
        sub_msg = {
            "method": "SUBSCRIBE",
            "params": [f"depth.{symbol}"],
            "id": 1,
        }
        await ws.send(json.dumps(sub_msg))
        print(f"✅ Subscribed to depth.{symbol}")

        while True:
            msg = await ws.recv()
            data = json.loads(msg).get("data", {})
            bids = data.get("b", [])
            asks = data.get("a", [])

            for price, size in bids:
                if float(size) == 0:
                    orderbook["bids"].pop(price, None)
                else:
                    orderbook["bids"][price] = size
            for price, size in asks:
                if float(size) == 0:
                    orderbook["asks"].pop(price, None)
                else:
                    orderbook["asks"][price] = size

async def analyze_and_trade(symbol, usdc_amount, interval, leverage):
    global has_position
    public_positions_checked = False

    while True:
        try:
            # Mise à jour local du volume
            bid_volume = sum(float(v) for v in orderbook["bids"].values())
            ask_volume = sum(float(v) for v in orderbook["asks"].values())
            print(f"📊 Bids volume: {bid_volume:.4f} | Asks volume: {ask_volume:.4f}")

            # Check si position ouverte via API une fois au début et ensuite on verrouille localement
            if not has_position and not public_positions_checked:
                positions = account.get_open_positions()
                for p in positions:
                    if p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0:
                        has_position = True
                        print("⏸️ Position déjà ouverte détectée via API")
                        break
                public_positions_checked = True

            # Ne rien faire si position active
            if has_position:
                print(f"⏸️ Position active, attente...")
                await asyncio.sleep(interval)
                continue

            # Signal simple selon asymétrie volume (sans seuil)
            if bid_volume > ask_volume * 1.1:
                signal = "BUY"
            elif ask_volume > bid_volume * 1.1:
                signal = "SELL"
            else:
                signal = "HOLD"

            print(f"Signal: {signal}")

            if signal != "HOLD":
                # Estimer la quantité approximative selon price approx (ex: midpoint)
                try:
                    best_bid = max(float(p) for p in orderbook["bids"]) if orderbook["bids"] else 0
                    best_ask = min(float(p) for p in orderbook["asks"]) if orderbook["asks"] else 0
                    price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
                except Exception:
                    price = 0

                if price == 0:
                    print("⚠️ Prix non disponible, ordre ignoré")
                    await asyncio.sleep(interval)
                    continue

                quantity = usdc_amount * leverage / price

                if quantity < 0.0001:
                    print(f"⚠️ Quantité trop faible ({quantity:.6f}), ordre ignoré")
                    await asyncio.sleep(interval)
                    continue

                print(f"📤 Soumission ordre {signal} de {quantity:.6f} unités (~{usdc_amount*leverage} USDC)")

                open_position(symbol, usdc_amount * leverage, signal.lower())
                has_position = True  # verrou local activé

            else:
                print("⏸️ Pas de signal")

            await asyncio.sleep(interval)

        except Exception as e:
            print(f"⚠️ Erreur dans la boucle du bot: {e}")
            await asyncio.sleep(5)

async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 bot_orderbook.py <SYMBOL> <USDC_AMOUNT> [INTERVAL] [LEVERAGE]")
        sys.exit(1)

    symbol = sys.argv[1]
    usdc_amount = float(sys.argv[2])
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    leverage = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    task_ws = asyncio.create_task(websocket_orderbook(symbol))
    task_bot = asyncio.create_task(analyze_and_trade(symbol, usdc_amount, interval, leverage))

    await asyncio.gather(task_ws, task_bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stoppé")
