from bpx.account import Account

import os
public_key = os.environ.get("bpx_bot_public_key")
secret_key = os.environ.get("bpx_bot_secret_key")


def main():
    account = Account(public_key=public_key, secret_key=secret_key, window=5000, debug=False)
    infos = account.get_account()

    mapping = {
        "autoBorrowSettlements": "Auto règlement emprunt",
        "autoLend": "Auto prêt",
        "autoRealizePnl": "Auto réalisation PnL",
        "autoRepayBorrows": "Auto remboursement emprunts",
        "borrowLimit": "Limite d'emprunt (USD)",
        "futuresMakerFee": "Frais Futures Maker (bps)",
        "futuresTakerFee": "Frais Futures Taker (bps)",
        "leverageLimit": "Effet de levier max",
        "limitOrders": "Nb max d'ordres limit",
        "liquidating": "En liquidation",
        "positionLimit": "Limite de position (USD)",
        "spotMakerFee": "Frais Spot Maker (bps)",
        "spotTakerFee": "Frais Spot Taker (bps)",
        "triggerOrders": "Nb max d'ordres trigger"
    }

    print("[Infos du compte Backpack]\n")
    print(f"{'Nom':<35} | Valeur")
    print("-" * 55)
    for key, label in mapping.items():
        value = infos.get(key, "—")
        print(f"{label:<35} | {value}")

if __name__ == "__main__":
    main()
