from django import template

register = template.Library()


@register.filter
def group_by_vendor(items):
    """Group cart items by vendor, keeping first-seen order."""
    groups = {}
    for item in items:
        groups.setdefault(item.variant.product.vendor, []).append(item)
    return [
        {'vendor': v, 'lines': lines, 'subtotal': sum(i.line_total() for i in lines)}
        for v, lines in groups.items()
    ]
