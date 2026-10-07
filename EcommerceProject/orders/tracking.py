"""Customer-facing order status helpers (presentation only; no database access)."""
from collections import Counter

from .models import VendorOrder

S = VendorOrder.Status

# Happy-path steps shown on the tracking timeline, in order.
TRACK_STEPS = [
    (S.PENDING, 'Order placed'),
    (S.CONFIRMED, 'Confirmed'),
    (S.PROCESSING, 'Processing'),
    (S.PACKED, 'Packed'),
    (S.SHIPPED, 'Shipped'),
    (S.DELIVERED, 'Delivered'),
]
_STEP_INDEX = {key: i for i, (key, _) in enumerate(TRACK_STEPS)}

# States that end the happy path; shown as a banner instead of a timeline.
EXCEPTION_MESSAGES = {
    S.CANCELLED: ('danger', 'This part of your order was cancelled. Any reserved stock has been released.'),
    S.RETURNED: ('warning', 'The items from this seller were delivered and then returned.'),
    S.REFUNDED: ('info', 'The items from this seller were returned and refunded.'),
}

# Customers may cancel only while the seller has not started processing.
CUSTOMER_CANCELLABLE = {S.PENDING, S.CONFIRMED}


def build_timeline(status):
    """List of {'label', 'state'} dicts (state: done / current / todo), or None for cancelled/returned/refunded."""
    if status not in _STEP_INDEX:
        return None
    idx = _STEP_INDEX[status]
    finished = status == S.DELIVERED
    steps = []
    for i, (_, label) in enumerate(TRACK_STEPS):
        if i < idx or finished:
            state = 'done'
        elif i == idx:
            state = 'current'
        else:
            state = 'todo'
        steps.append({'label': label, 'state': state})
    return steps


def decorate_vendor_orders(vendor_orders):
    """Attach `timeline`, `exception` and `can_cancel` to already-loaded vendor orders."""
    vendor_orders = list(vendor_orders)
    for vo in vendor_orders:
        vo.timeline = build_timeline(vo.status)
        vo.exception = EXCEPTION_MESSAGES.get(vo.status)
        vo.can_cancel = vo.status in CUSTOMER_CANCELLABLE
    return vendor_orders


def summarize_statuses(vendor_orders):
    """One-line overall status for the My Orders list, from already-loaded vendor orders.

    All same status -> that label; otherwise a count per status ("1 Shipped, 1 Pending").
    """
    counts = Counter(vo.status for vo in vendor_orders)
    if not counts:
        return '', ''
    if len(counts) == 1:
        status = next(iter(counts))
        return VendorOrder.Status(status).label, status
    ordered = [s for s, _ in VendorOrder.Status.choices if s in counts]
    text = ', '.join(f"{counts[s]} {VendorOrder.Status(s).label}" for s in ordered)
    return text, 'mixed'
