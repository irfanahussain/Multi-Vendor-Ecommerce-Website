from django import template

register = template.Library()

# Status value -> site badge classes (the .badge-* classes live in static/css/style.css).
_BADGES = {
    # good / done
    'approved': 'badge-approved', 'active': 'badge-approved', 'completed': 'badge-approved', 'paid': 'badge-approved',
    'delivered': 'badge-approved',
    # waiting / in progress
    'pending': 'badge-pending', 'requested': 'badge-pending', 'under_review': 'badge-pending',
    'processing': 'badge-pending', 'confirmed': 'badge-pending', 'packed': 'badge-pending',
    'shipped': 'bg-info text-dark',
    # bad
    'rejected': 'badge-rejected', 'failed': 'badge-rejected', 'cancelled': 'badge-rejected',
    # closed / neutral
    'inactive': 'badge-oos', 'returned': 'badge-oos', 'refunded': 'badge-oos',
}


@register.filter
def admin_badge(status):
    """Badge classes for a status value, e.g. {{ obj.status|admin_badge }}."""
    return _BADGES.get(status, 'bg-secondary')
