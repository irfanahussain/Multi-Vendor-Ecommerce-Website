"""Money display helper.

Every rupee amount on the site is shown with at most two decimal places. Only the
display changes: stored database values and calculations are never rounded here.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_PAISE = Decimal('0.01')


def format_money(value):
    """Return `value` as a plain string with exactly two decimals.

    Decimal('1653.5000000000') -> '1653.50', Decimal('152.7000000000') -> '152.70',
    Decimal('100.00') -> '100.00', None -> '0.00'. Values are rounded half-up to paise.
    """
    if value is None or value == '':
        value = 0
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if not amount.is_finite():
        return str(value)
    rounded = amount.quantize(_PAISE, rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)  # avoid showing "-0.00"
    return f'{rounded:.2f}'
