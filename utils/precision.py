from decimal import Decimal, ROUND_DOWN

def adjust_to_step(value: float, step: float) -> float:
    """
    Arrondit une valeur vers le bas en respectant l'incrément (step).
    """
    if step == 0:
        return value
    return float(Decimal(value).quantize(Decimal(str(step)), rounding=ROUND_DOWN))