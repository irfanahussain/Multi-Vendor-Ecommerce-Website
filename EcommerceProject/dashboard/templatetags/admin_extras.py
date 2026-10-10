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


@register.simple_tag
def pending_approval_count():
    """Vendors + products waiting for approval, shown as the header notification badge.
    Only called from admin_base.html, which every admin page extends."""
    from vendors.models import VendorStore
    from catalog.models import Product
    return (VendorStore.objects.filter(status=VendorStore.Status.PENDING).count()
            + Product.objects.filter(status=Product.Status.PENDING).count())
