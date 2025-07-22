import asyncio
import json
import websockets
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from execute.open_position_usdc import open_position
from execute.close_position_percent import close_position_percent
from bpx.account import Account

account = Account(
    public_key=os.environ.get("bpx_bot_public_key"),
    secret_key=os.environ.get("bpx_bot_secret_key"),
)

orderbook = {"bids": {}, "asks": {}}
has_position = False  # verrou local
entry_price = None    # pour suivre le prix d'entrée
direction = None      # long ou short

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

def is_position_open(symbol: str) -> bool:
    try:
        positions = account.get_open_positions()
        return any(
            p.get("symbol") == symbol and abs(float(p.get("quantity", 0))) > 0
            for p in positions
        )
    except Exception as e:
        print(f"⚠️ Erreur lors de la vérification de position: {e}")
        return False

def get_mid_price():
    try:
        best_bid = max(float(p) for p in orderbook["bids"]) if orderbook["bids"] else 0
        best_ask = min(float(p) for p in orderbook["asks"]) if orderbook["asks"] else 0
        return (best_bid + best_ask) / 2 if best_bid and best_ask else 0
    except:
        return 0

async def analyze_and_trade(symbol, usdc_amount, interval, leverage, tp_pct=1.0):
    global has_position, entry_price, direction

    while True:
        try:
            # Mise à jour volume
            bid_volume = sum(float(v) for v in orderbook["bids"].values())
            ask_volume = sum(float(v) for v in orderbook["asks"].values())
            print(f"📊 Bids volume: {bid_volume:.4f} | Asks volume: {ask_volume:.4f}")

            # Vérification périodique si position encore ouverte
            if has_position:
                if not is_position_open(symbol):
                    print("✅ Position fermée détectée via API")
                    has_position = False
                    entry_price = None
                    direction = None
                else:
                    # Vérifier TP (Take Profit)
                    current_price = get_mid_price()
                    if current_price > 0 and entry_price:
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                        if direction == "short":
                            pnl_pct *= -1
                        print(f"📈 PnL % estimée : {pnl_pct:.2f}%")

                        if pnl_pct >= tp_pct:
                            print(f"🎯 Take Profit atteint ({pnl_pct:.2f}%), fermeture position...")
                            close_position_percent(public_key, secret_key, symbol, 100)
                            has_position = False
                            entry_price = None
                            direction = None
                    await asyncio.sleep(interval)
                    continue

            # Signal basé sur volume asymétrique
            if bid_volume > ask_volume * 1.1:
                signal = "BUY"
            elif ask_volume > bid_volume * 1.1:
                signal = "SELL"
            else:
                signal = "HOLD"

            print(f"Signal: {signal}")

            if is_position_open(symbol):
                print("⏸️ Une position est déjà ouverte pour ce symbole, aucun ordre ne sera passé.")
                has_position = True
                await asyncio.sleep(interval)
                continue
            
            if signal != "HOLD":
                price = get_mid_price()
                if price == 0:
                    print("⚠️ Prix non disponible, ordre ignoré")
                    await asyncio.sleep(interval)
                    continue

                quantity = usdc_amount * leverage / price
                if quantity < 0.0001:
                    print(f"⚠️ Quantité trop faible ({quantity:.6f}), ordre ignoré")
                    await asyncio.sleep(interval)
                    continue

                direction = "long" if signal == "BUY" else "short"
                print(f"📤 Soumission ordre {signal} de {quantity:.6f} unités (~{usdc_amount*leverage} USDC)")
                open_position(symbol, usdc_amount * leverage, direction)
                has_position = True
                entry_price = price
                print(f"🔒 Position ouverte à {entry_price:.4f} en {direction}")

            else:
                print("⏸️ Pas de signal")

            await asyncio.sleep(interval)

        except Exception as e:
            print(f"⚠️ Erreur dans la boucle du bot: {e}")
            await asyncio.sleep(5)

async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 bot_orderbook.py <SYMBOL> <USDC_AMOUNT> [INTERVAL] [LEVERAGE] [TP_PCT]")
        sys.exit(1)

    symbol = sys.argv[1]
    usdc_amount = float(sys.argv[2])
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    leverage = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    tp_pct = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0  # take profit en %

    task_ws = asyncio.create_task(websocket_orderbook(symbol))
    task_bot = asyncio.create_task(analyze_and_trade(symbol, usdc_amount, interval, leverage, tp_pct))

    await asyncio.gather(task_ws, task_bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stoppé")
