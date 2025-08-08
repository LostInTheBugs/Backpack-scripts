# utils/order_validator.py

from decimal import Decimal, ROUND_DOWN

def is_order_valid_for_market(quantity, price, step_size, tick_size):
    """
    Vérifie si la quantité et le prix sont valides selon stepSize et tickSize du marché.
    """
    quantity = Decimal(str(quantity))
    price = Decimal(str(price))
    step_size = Decimal(str(step_size))
    tick_size = Decimal(str(tick_size))

    # Quantité conforme
    valid_qty = (quantity % step_size).quantize(Decimal("1e-8")) == 0
    # Prix conforme
    valid_price = (price % tick_size).quantize(Decimal("1e-8")) == 0

    return valid_qty, valid_price

def adjust_to_step(value, step):
    """
    Arrondit vers le bas la valeur pour respecter un step (ex: stepSize ou tickSize).
    """
    value = Decimal(str(value))
    step = Decimal(str(step))
    adjusted = (value // step) * step
    return float(adjusted.quantize(step))
