from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def rub(value):
    """1234.5 -> «1 234,50 ₽»."""
    try:
        number = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


@register.filter
def rub0(value):
    """1234.5 -> «1 235 ₽» — для крупных KPI."""
    try:
        number = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.0f}".replace(",", " ") + " ₽"


@register.filter
def dict_get(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None


@register.filter
def mul(value, arg):
    try:
        return round(float(value) * float(arg), 1)
    except (TypeError, ValueError):
        return value
