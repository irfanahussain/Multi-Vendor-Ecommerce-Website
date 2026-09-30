def cart_summary(request):
    cart_count = 0
    active_orders = 0
    if request.user.is_authenticated:
        cart = getattr(request.user, 'cart', None)
        if cart:
            cart_count = cart.total_items()
        # Orders that still have something in progress (not delivered/cancelled/returned/refunded)
        from .models import Order, VendorOrder
        in_progress = [
            VendorOrder.Status.PENDING, VendorOrder.Status.CONFIRMED,
            VendorOrder.Status.PROCESSING, VendorOrder.Status.PACKED,
            VendorOrder.Status.SHIPPED,
        ]
        active_orders = (
            Order.objects.filter(customer=request.user, vendor_orders__status__in=in_progress)
            .distinct().count()
        )
    return {'cart_item_count': cart_count, 'active_order_count': active_orders}
