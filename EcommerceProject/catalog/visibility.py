"""Which products a shopper may see and buy.

A product is sellable when:
  1. its status is ACTIVE (admin-approved and not switched off), and
  2. its vendor's store is NOT Rejected and NOT Inactive.

Only those two store statuses hide products. A vendor with no store record is not hidden (this was the
behaviour before and no test or flow relies on changing it). Other vendors' and products' statuses are
never changed by this module: it only filters what is shown and sold.
"""
from django.db.models import Q

from vendors.models import VendorStore
from .models import Product

HIDDEN_STORE_STATUSES = (VendorStore.Status.REJECTED, VendorStore.Status.INACTIVE)
VISIBLE_STORE_STATUSES = [v for v in VendorStore.Status.values if v not in HIDDEN_STORE_STATUSES]


def _store_allows_q(prefix=''):
    return (Q(**{f'{prefix}vendor__store__isnull': True})
            | Q(**{f'{prefix}vendor__store__status__in': VISIBLE_STORE_STATUSES}))


def visible_products(queryset=None):
    """ACTIVE products whose store is not rejected/inactive. Pass a queryset to narrow it further."""
    base = Product.objects.all() if queryset is None else queryset
    return base.filter(status=Product.Status.ACTIVE).filter(_store_allows_q())


def product_is_sellable(product):
    if product.status != Product.Status.ACTIVE:
        return False
    store_status = VendorStore.objects.filter(vendor_id=product.vendor_id).values_list('status', flat=True).first()
    return store_status is None or store_status not in HIDDEN_STORE_STATUSES
