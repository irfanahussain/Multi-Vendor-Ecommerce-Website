"""Writes Activity Log entries for real actions.

Summaries use record ids and status names only. Never pass emails, names, phone numbers,
addresses, payment details or passwords into these helpers.
"""
from .models import ActivityLog

A = ActivityLog.Action


def _write(action, summary, actor, target):
    target_type, target_id = target
    return ActivityLog.objects.create(
        actor=actor if (actor is not None and actor.is_authenticated) else None,
        action=action,
        summary=summary[:255],
        target_type=target_type,
        target_id=target_id,
    )


def log_vendor_status(actor, store):
    return _write(A.VENDOR_STATUS, f'Store #{store.pk} is now {store.get_status_display()}',
                  actor, ('vendor_store', store.pk))


def log_product_status(actor, product):
    return _write(A.PRODUCT_STATUS, f'Product #{product.pk} is now {product.get_status_display()}',
                  actor, ('product', product.pk))


def log_order_status(actor, vendor_order, status_label):
    return _write(A.ORDER_STATUS, f'Sub-order #{vendor_order.pk} is now {status_label}',
                  actor, ('vendor_order', vendor_order.pk))


def log_stock(actor, variant, change):
    return _write(A.STOCK_ADJUST, f'Variant #{variant.pk} stock changed by {change:+d}',
                  actor, ('product_variant', variant.pk))


def log_customer_block(actor, customer):
    state = 'active' if customer.is_active else 'blocked'
    return _write(A.CUSTOMER_BLOCK, f'Customer #{customer.pk} is now {state}',
                  actor, ('customer', customer.pk))


def log_coupon_created(actor, coupon):
    return _write(A.COUPON_CREATED, f'Coupon #{coupon.pk} created', actor, ('coupon', coupon.pk))


def log_refund_status(actor, refund):
    return _write(A.REFUND_STATUS, f'Refund #{refund.pk} is now {refund.get_status_display()}',
                  actor, ('refund', refund.pk))
