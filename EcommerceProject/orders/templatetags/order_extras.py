from django import template

register = template.Library()

_BADGES = {
    'pending': 'badge-pending', 'confirmed': 'badge-pending', 'processing': 'badge-pending', 'packed': 'badge-pending',
    'shipped': 'bg-info text-dark', 'delivered': 'badge-approved',
    'cancelled': 'badge-rejected', 'returned': 'badge-oos', 'refunded': 'badge-oos',
    'mixed': 'bg-secondary',
}


@register.filter
def status_badge(status):
    """Bootstrap/site badge classes for a vendor-order status key."""
    return _BADGES.get(status, 'bg-secondary')
