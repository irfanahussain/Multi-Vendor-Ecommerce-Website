"""Return and refund state changes that touch stock and sub-order money.

Every function here runs inside one database transaction and takes row locks, so two admins (or an
admin and a customer) cannot act on the same return or the same units at the same time.
"""
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from catalog.models import ProductVariant, StockHistory
from orders.finance import recalculate_vendor_order
from orders.models import OrderItem, VendorOrder

from .models import ReturnRequest

RS = ReturnRequest.Status


class ReturnError(Exception):
    """A return change that is not allowed right now. The message is safe to show the user."""


def units_claimed(order_item):
    """Units on this item that are in a return request which is not rejected."""
    return (ReturnRequest.objects.filter(order_item=order_item).exclude(status=RS.REJECTED)
            .aggregate(total=Sum('quantity'))['total'] or 0)


def _refunded_units(order_item):
    return (ReturnRequest.objects.filter(order_item=order_item, status=RS.REFUNDED)
            .aggregate(total=Sum('quantity'))['total'] or 0)


def refresh_vendor_order_status(vendor_order):
    """Move a delivered sub-order to Returned or Refunded, but only when EVERY unit has come back.

    Partial returns leave the sub-order Delivered: the other units are still with the customer.
      - all units received back            -> RETURNED
      - all units received AND refunded    -> REFUNDED
      - anything less                      -> DELIVERED (unchanged)
    """
    if vendor_order.status not in (VendorOrder.Status.DELIVERED, VendorOrder.Status.RETURNED,
                                   VendorOrder.Status.REFUNDED):
        return vendor_order
    items = list(vendor_order.items.all())
    if not items:
        return vendor_order
    received = all(item.returned_quantity >= item.quantity for item in items)
    refunded = received and all(_refunded_units(item) >= item.quantity for item in items)
    if refunded:
        target = VendorOrder.Status.REFUNDED
    elif received:
        target = VendorOrder.Status.RETURNED
    else:
        target = VendorOrder.Status.DELIVERED
    if vendor_order.status != target:
        vendor_order.status = target
        vendor_order.save()
    return vendor_order


def _lock_vendor_order_for(order_item):
    return VendorOrder.objects.select_for_update().get(pk=order_item.vendor_order_id)


def mark_return_received(return_request_pk):
    """Approved -> Returned: the goods have arrived. Restocks the units once, updates the sub-order.

    Restocking is tied to this transition: it can only run for an APPROVED request that has no
    `received_at`, and the request row is locked, so a second call cannot restock the same units.
    """
    with transaction.atomic():
        rr = (ReturnRequest.objects.select_for_update()
              .get(pk=return_request_pk))
        if rr.status != RS.APPROVED or rr.received_at is not None:
            raise ReturnError('This return has already been received, or it is not approved.')
        item = OrderItem.objects.select_for_update().get(pk=rr.order_item_id)
        vendor_order = _lock_vendor_order_for(item)

        rr.status = RS.RETURNED
        rr.received_at = timezone.now()
        rr.save(update_fields=['status', 'received_at'])

        OrderItem.objects.filter(pk=item.pk).update(returned_quantity=F('returned_quantity') + rr.quantity)
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                stock_quantity=F('stock_quantity') + rr.quantity)
            StockHistory.objects.create(
                variant_id=item.variant_id, change_quantity=rr.quantity,
                reason=StockHistory.Reason.RETURN, note=f'Return #{rr.pk} received',
            )
        recalculate_vendor_order(vendor_order)
        refresh_vendor_order_status(vendor_order)
    return rr


def mark_refund_completed(return_request):
    """Refund completed: the return becomes Refunded and the sub-order status is re-checked."""
    with transaction.atomic():
        rr = ReturnRequest.objects.select_for_update().get(pk=return_request.pk)
        rr.status = RS.REFUNDED
        rr.save(update_fields=['status'])
        item = OrderItem.objects.get(pk=rr.order_item_id)
        refresh_vendor_order_status(_lock_vendor_order_for(item))
    return rr
