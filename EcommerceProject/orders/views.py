from django.shortcuts import render,redirect, get_object_or_404
import uuid
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalog.models import ProductVariant, StockHistory
from accounts.models import Address
from vendors.decorators import vendor_required
from .models import Cart, CartItem, Order, VendorOrder, OrderItem, Coupon
from .forms import CouponForm, CheckoutForm
# Create your views here.


SHIPPING_FLAT_CHARGE = Decimal('50.00')
FREE_SHIPPING_THRESHOLD = Decimal('500.00')
TAX_PERCENT = Decimal('5.00')
DEFAULT_COMMISSION_PERCENT = Decimal('10.00')


class CheckoutError(Exception):
    """Raised inside the checkout transaction to roll everything back."""


# Which statuses a vendor may move an order to, from the current status.
# RETURNED / REFUNDED are set by the returns flow, never by the vendor.
VENDOR_TRANSITIONS = {
    VendorOrder.Status.PENDING: {VendorOrder.Status.CONFIRMED, VendorOrder.Status.CANCELLED},
    VendorOrder.Status.CONFIRMED: {VendorOrder.Status.PROCESSING, VendorOrder.Status.CANCELLED},
    VendorOrder.Status.PROCESSING: {VendorOrder.Status.PACKED, VendorOrder.Status.CANCELLED},
    VendorOrder.Status.PACKED: {VendorOrder.Status.SHIPPED, VendorOrder.Status.CANCELLED},
    VendorOrder.Status.SHIPPED: {VendorOrder.Status.DELIVERED},
}


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def _parse_quantity(raw, default=None):
    """Return an int, or `default` if the input is junk."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _calculate_totals(subtotal, coupon):
    discount = coupon.calculate_discount(subtotal) if coupon else Decimal('0')
    taxable = subtotal - discount
    tax_amount = (taxable * TAX_PERCENT / 100).quantize(Decimal('0.01'))
    shipping_charge = Decimal('0') if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FLAT_CHARGE
    total = taxable + tax_amount + shipping_charge
    return discount, tax_amount, shipping_charge, total


def _restock_vendor_order(vendor_order, note):
    """Give stock back for every item of a cancelled vendor order."""
    for item in vendor_order.items.select_related('variant'):
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )
            StockHistory.objects.create(
                variant=item.variant, change_quantity=item.quantity,
                reason=StockHistory.Reason.RETURN, note=note,
            )


@login_required
def cart_view(request):
    cart = _get_or_create_cart(request.user)
    coupon_code = request.session.get('coupon_code')
    coupon = None
    discount = Decimal('0')
    if coupon_code:
        coupon = Coupon.objects.filter(code=coupon_code).first()
        if coupon:
            valid, _ = coupon.is_valid_now()
            if valid:
                discount = coupon.calculate_discount(cart.subtotal())
            else:
                del request.session['coupon_code']
                coupon = None

    return render(request, 'orders/cart.html', {
        'cart': cart,
        'coupon_form': CouponForm(),
        'coupon': coupon,
        'discount': discount,
    })


@require_POST
@login_required
def cart_add(request, variant_id):
    variant = get_object_or_404(ProductVariant, pk=variant_id, is_active=True)
    quantity = _parse_quantity(request.POST.get('quantity', 1))
    if quantity is None or quantity < 1:
        messages.error(request, 'Please enter a valid quantity.')
        return redirect(variant.product.get_absolute_url())

    cart = _get_or_create_cart(request.user)
    existing = CartItem.objects.filter(cart=cart, variant=variant).first()
    new_quantity = (existing.quantity if existing else 0) + quantity

    if new_quantity > variant.stock_quantity:
        messages.error(request, f"Only {variant.stock_quantity} in stock for {variant.product.name}.")
        return redirect(variant.product.get_absolute_url())

    CartItem.objects.update_or_create(
        cart=cart, variant=variant, defaults={'quantity': new_quantity}
    )
    messages.success(request, f"Added {variant.product.name} to cart.")
    return redirect('orders:cart')


@require_POST
@login_required
def cart_update(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    quantity = _parse_quantity(request.POST.get('quantity'))
    if quantity is None:
        messages.error(request, 'Please enter a valid quantity.')
    elif quantity <= 0:
        item.delete()
    elif quantity > item.variant.stock_quantity:
        messages.error(request, "Not enough stock available.")
    else:
        item.quantity = quantity
        item.save()
    return redirect('orders:cart')


@require_POST
@login_required
def cart_remove(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, 'Item removed from cart.')
    return redirect('orders:cart')


@require_POST
@login_required
def apply_coupon(request):
    form = CouponForm(request.POST)
    if form.is_valid():
        code = form.cleaned_data['code'].strip().upper()
        coupon = Coupon.objects.filter(code=code).first()
        if not coupon:
            messages.error(request, 'Invalid coupon code.')
        else:
            valid, reason = coupon.is_valid_now()
            if not valid:
                messages.error(request, reason)
            else:
                # Enforce per-customer usage limit
                used_by_customer = Order.objects.filter(customer=request.user, coupon=coupon).count()
                if used_by_customer >= coupon.customer_usage_limit:
                    messages.error(request, "You've already used this coupon the maximum number of times.")
                else:
                    request.session['coupon_code'] = coupon.code
                    messages.success(request, f'Coupon "{coupon.code}" applied!')
    return redirect('orders:cart')


@require_POST
@login_required
def remove_coupon(request):
    request.session.pop('coupon_code', None)
    return redirect('orders:cart')


@login_required
def checkout(request):
    cart = _get_or_create_cart(request.user)
    if not cart.items.exists():
        messages.error(request, 'Your cart is empty.')
        return redirect('orders:cart')

    addresses = request.user.addresses.all()
    coupon_code = request.session.get('coupon_code')
    coupon = Coupon.objects.filter(code=coupon_code).first() if coupon_code else None

    subtotal = cart.subtotal()
    discount, tax_amount, shipping_charge, total = _calculate_totals(subtotal, coupon)

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            address = get_object_or_404(Address, pk=form.cleaned_data['address_id'], user=request.user)
            try:
                with transaction.atomic():
                    order = _place_order(request, cart, address, form.cleaned_data['payment_method'], coupon)
            except CheckoutError as exc:
                messages.error(request, str(exc))
                return redirect('orders:cart')

            request.session.pop('coupon_code', None)
            messages.success(request, f'Order {order.order_number} placed successfully!')
            return redirect('orders:order_detail', order_number=order.order_number)
    else:
        form = CheckoutForm()

    return render(request, 'orders/checkout.html', {
        'cart': cart, 'addresses': addresses, 'form': form,
        'subtotal': subtotal, 'discount': discount, 'tax_amount': tax_amount,
        'shipping_charge': shipping_charge, 'total': total, 'coupon': coupon,
    })


def _place_order(request, cart, address, payment_method, coupon):
    """Runs inside transaction.atomic(); any CheckoutError rolls everything back."""
    cart_items = list(cart.items.select_related('variant__product__vendor'))
    if not cart_items:
        raise CheckoutError('Your cart is empty.')

    # Lock the coupon row and re-validate it so two checkouts can't both
    # use the last remaining redemption.
    if coupon:
        coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
        valid, reason = coupon.is_valid_now()
        if not valid:
            raise CheckoutError(reason)
        used = Order.objects.filter(customer=request.user, coupon=coupon).count()
        if used >= coupon.customer_usage_limit:
            raise CheckoutError("You've already used this coupon the maximum number of times.")

    subtotal = sum(i.line_total() for i in cart_items)
    discount, tax_amount, shipping_charge, total = _calculate_totals(subtotal, coupon)

    order = Order.objects.create(
        order_number=f"ORD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        customer=request.user,
        shipping_address=address,
        coupon=coupon,
        subtotal=subtotal,
        discount_amount=discount,
        tax_amount=tax_amount,
        shipping_charge=shipping_charge,
        total_amount=total,
        payment_method=payment_method,
        payment_status=Order.PaymentStatus.PENDING,
    )

    items_by_vendor = {}
    for item in cart_items:
        items_by_vendor.setdefault(item.variant.product.vendor, []).append(item)

    for vendor, items in items_by_vendor.items():
        vendor_order = VendorOrder.objects.create(
            order=order, vendor=vendor,
            subtotal=sum(i.line_total() for i in items),
            commission_percent=DEFAULT_COMMISSION_PERCENT,
        )
        for i in items:
            # Atomic compare-and-subtract: only succeeds if enough stock is
            # still there at this exact moment, so stock can never go negative.
            updated = ProductVariant.objects.filter(
                pk=i.variant_id, is_active=True, stock_quantity__gte=i.quantity
            ).update(stock_quantity=F('stock_quantity') - i.quantity)
            if not updated:
                raise CheckoutError(f"'{i.variant.product.name}' no longer has enough stock.")

            OrderItem.objects.create(
                vendor_order=vendor_order,
                variant=i.variant,
                product_name=i.variant.product.name,
                variant_name=i.variant.name,
                price=i.variant.effective_price,
                quantity=i.quantity,
            )
            StockHistory.objects.create(
                variant=i.variant, change_quantity=-i.quantity,
                reason=StockHistory.Reason.SALE, note=f"Order {order.order_number}",
            )

    if coupon:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F('used_count') + 1)

    cart.items.all().delete()
    return order


@login_required
def order_list(request):
    orders = (Order.objects.filter(customer=request.user)
              .prefetch_related('vendor_orders__items').order_by('-created_at'))
    page_obj = Paginator(orders, 10).get_page(request.GET.get('page'))
    return render(request, 'orders/order_list.html', {'orders': page_obj, 'page_obj': page_obj})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    return render(request, 'orders/order_detail.html', {'order': order})


@require_POST
@login_required
def cancel_vendor_order(request, pk):
    with transaction.atomic():
        vendor_order = get_object_or_404(
            VendorOrder.objects.select_for_update(), pk=pk, order__customer=request.user
        )
        if vendor_order.status in (VendorOrder.Status.PENDING, VendorOrder.Status.CONFIRMED):
            vendor_order.status = VendorOrder.Status.CANCELLED
            vendor_order.save()
            _restock_vendor_order(vendor_order, f"Cancelled {vendor_order}")
            messages.success(request, 'Order cancelled.')
        else:
            messages.error(request, 'This order can no longer be cancelled.')
    return redirect('orders:order_detail', order_number=vendor_order.order.order_number)


# ---------- Vendor order management ----------

@vendor_required
def vendor_order_list(request):
    vendor_orders = (VendorOrder.objects.filter(vendor=request.user)
                     .select_related('order').order_by('-created_at'))
    page_obj = Paginator(vendor_orders, 15).get_page(request.GET.get('page'))
    return render(request, 'orders/vendor_order_list.html',
                  {'vendor_orders': page_obj, 'page_obj': page_obj})


@vendor_required
def vendor_order_detail(request, pk):
    if request.method == 'POST':
        new_status = request.POST.get('status')
        with transaction.atomic():
            vendor_order = get_object_or_404(
                VendorOrder.objects.select_for_update(), pk=pk, vendor=request.user
            )
            allowed = VENDOR_TRANSITIONS.get(vendor_order.status, set())
            if new_status not in allowed:
                messages.error(request, 'That status change is not allowed.')
            else:
                vendor_order.status = new_status
                vendor_order.save()
                if new_status == VendorOrder.Status.CANCELLED:
                    _restock_vendor_order(vendor_order, f"Cancelled by vendor {vendor_order}")
                messages.success(
                    request,
                    f'Order status updated to {VendorOrder.Status(new_status).label}.',
                )
        return redirect('orders:vendor_order_detail', pk=pk)

    vendor_order = get_object_or_404(VendorOrder, pk=pk, vendor=request.user)
    allowed = VENDOR_TRANSITIONS.get(vendor_order.status, set())
    next_statuses = [(v, l) for v, l in VendorOrder.Status.choices if v in allowed]
    return render(request, 'orders/vendor_order_detail.html', {
        'vendor_order': vendor_order, 'next_statuses': next_statuses,
    })
