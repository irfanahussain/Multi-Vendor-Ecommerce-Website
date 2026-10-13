"""Money rules for orders, commission and vendor earnings. Single source for the aggregates.

Definitions (per VendorOrder, i.e. one vendor's part of a customer order):

  subtotal          gross value of the items sold, at the price snapshot taken at checkout.
                    Never changes after the order is placed.
  returned_amount   price x units that have been RECEIVED BACK through an approved return
                    (OrderItem.returned_quantity). Set when the goods arrive, not when requested,
                    and not reduced by a refund.
  net_subtotal      subtotal - returned_amount.
  commission        net_subtotal x commission_percent (default 10%), 2 dp.
  vendor_earning    net_subtotal - commission.

Coupons (platform-funded, unchanged): a coupon reduces the CUSTOMER's order total (Order.discount_amount),
but no VendorOrder subtotal is reduced by it. So commission and vendor earnings are calculated on the
gross item value and the platform bears the discount. Refund amounts are price x units, which is also
gross (see returns_app/services.py and the open decision in the audit report).

Sales on dashboards that are vendor- or sub-order-based use net_subtotal. Customer-order totals
(Order.total_amount, the admin overview's Sales card) remain gross customer payments.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F

MONEY = DecimalField(max_digits=12, decimal_places=2)

# Sum this over VendorOrder querysets to get net sales (gross sub-order value minus returns).
NET_SUBTOTAL = ExpressionWrapper(F('subtotal') - F('returned_amount'), output_field=MONEY)

# Sum this over OrderItem querysets to get the net line value (price x units not returned).
LINE_NET = ExpressionWrapper(F('price') * (F('quantity') - F('returned_quantity')), output_field=MONEY)


def recalculate_vendor_order(vendor_order):
    """Recompute returned_amount from the item rows, then commission and earnings (via save)."""
    returned = Decimal('0')
    for item in vendor_order.items.all():
        returned += item.price * item.returned_quantity
    vendor_order.returned_amount = returned
    vendor_order.save()
    return vendor_order
