"""`{{ amount|money }}` renders a rupee amount with at most two decimal places.

Loaded as a built-in in settings.TEMPLATES, so templates need no `{% load %}` line.
The ₹ symbol stays in the template next to the filter, e.g. ₹{{ order.total_amount|money }}.
"""
from django import template

from catalog.money import format_money

register = template.Library()


@register.filter(name='money')
def money(value):
    return format_money(value)
