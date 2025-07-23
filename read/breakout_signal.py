# strategies/breakout_signal.py

def breakout_signal(ohlcv):
    """
    Analyse des chandelles pour détecter un breakout.
    Renvoie : "BUY", "SELL" ou None
    """
    if len(ohlcv) < 2:
        return None

    last = ohlcv[-1]
    prev = ohlcv[-2]

    # Exemple : breakout haussier si close dépasse high précédent
    if last['close'] > prev['high']:
        return "BUY"
    # Exemple : breakout baissier si close passe sous low précédent
    elif last['close'] < prev['low']:
        return "SELL"

    return None
