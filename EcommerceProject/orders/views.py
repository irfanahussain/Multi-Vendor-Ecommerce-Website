from django.shortcuts import render,redirect, get_object_or_404
import uuid
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
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


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


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
    cart = _get_or_create_cart(request.user)
    quantity = int(request.POST.get('quantity', 1))

    item, created = CartItem.objects.get_or_create(cart=cart, variant=variant, defaults={'quantity': 0})
    new_quantity = item.quantity + quantity

    if new_quantity > variant.stock_quantity:
        messages.error(request, f"Only {variant.stock_quantity} in stock for {variant.product.name}.")
        if not created:
            pass
        else:
            item.delete()
        return redirect(variant.product.get_absolute_url())

    item.quantity = new_quantity
    item.save()
    messages.success(request, f"Added {variant.product.name} to cart.")
    return redirect('orders:cart')


@require_POST
@login_required
def cart_update(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    quantity = int(request.POST.get('quantity', 1))
    if quantity <= 0:
        item.delete()
    elif quantity > item.variant.stock_quantity:
        messages.error(request, "Not enough stock available.")
    else:
        item.quantity = quantity
        item.save()
    return redirect('orders:cart')


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
    discount = coupon.calculate_discount(subtotal) if coupon else Decimal('0')
    taxable = subtotal - discount
    tax_amount = (taxable * TAX_PERCENT / 100).quantize(Decimal('0.01'))
    shipping_charge = Decimal('0') if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FLAT_CHARGE
    total = taxable + tax_amount + shipping_charge

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            address = get_object_or_404(Address, pk=form.cleaned_data['address_id'], user=request.user)

            # Re-validate stock right before committing (in case something changed)
            for item in cart.items.select_related('variant'):
                if item.quantity > item.variant.stock_quantity:
                    messages.error(request, f"'{item.variant.product.name}' no longer has enough stock.")
                    return redirect('orders:cart')

            with transaction.atomic():
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
                    payment_method=form.cleaned_data['payment_method'],
                    payment_status=Order.PaymentStatus.PENDING,
                )

                # Group cart items by vendor -> one VendorOrder each
                items_by_vendor = {}
                for item in cart.items.select_related('variant__product__vendor'):
                    vendor = item.variant.product.vendor
                    items_by_vendor.setdefault(vendor, []).append(item)

                for vendor, items in items_by_vendor.items():
                    vendor_subtotal = sum(i.line_total() for i in items)
                    vendor_order = VendorOrder.objects.create(
                        order=order, vendor=vendor,
                        subtotal=vendor_subtotal,
                        commission_percent=DEFAULT_COMMISSION_PERCENT,
                    )
                    for i in items:
                        OrderItem.objects.create(
                            vendor_order=vendor_order,
                            variant=i.variant,
                            product_name=i.variant.product.name,
                            variant_name=i.variant.name,
                            price=i.variant.effective_price,
                            quantity=i.quantity,
                        )
                        # Deduct stock + record history
                        i.variant.stock_quantity -= i.quantity
                        i.variant.save()
                        StockHistory.objects.create(
                            variant=i.variant, change_quantity=-i.quantity,
                            reason=StockHistory.Reason.SALE, note=f"Order {order.order_number}",
                        )

                if coupon:
                    coupon.used_count += 1
                    coupon.save()

                cart.items.all().delete()
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


@login_required
def order_list(request):
    orders = Order.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'orders/order_list.html', {'orders': orders})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, customer=request.user)
    return render(request, 'orders/order_detail.html', {'order': order})


@require_POST
@login_required
def cancel_vendor_order(request, pk):
    vendor_order = get_object_or_404(VendorOrder, pk=pk, order__customer=request.user)
    if vendor_order.status in (VendorOrder.Status.PENDING, VendorOrder.Status.CONFIRMED):
        vendor_order.status = VendorOrder.Status.CANCELLED
        vendor_order.save()
        # restock cancelled items
        for item in vendor_order.items.all():
            if item.variant:
                item.variant.stock_quantity += item.quantity
                item.variant.save()
                StockHistory.objects.create(
                    variant=item.variant, change_quantity=item.quantity,
                    reason=StockHistory.Reason.RETURN, note=f"Cancelled {vendor_order}",
                )
        messages.success(request, 'Order cancelled.')
    else:
        messages.error(request, 'This order can no longer be cancelled.')
    return redirect('orders:order_detail', order_number=vendor_order.order.order_number)


# ---------- Vendor order management ----------

@vendor_required
def vendor_order_list(request):
    vendor_orders = VendorOrder.objects.filter(vendor=request.user).order_by('-created_at')
    return render(request, 'orders/vendor_order_list.html', {'vendor_orders': vendor_orders})


@vendor_required
def vendor_order_detail(request, pk):
    vendor_order = get_object_or_404(VendorOrder, pk=pk, vendor=request.user)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = dict(VendorOrder.Status.choices)
        if new_status in valid_statuses:
            vendor_order.status = new_status
            vendor_order.save()
            messages.success(request, f'Order status updated to {valid_statuses[new_status]}.')
        return redirect('orders:vendor_order_detail', pk=pk)
    return render(request, 'orders/vendor_order_detail.html', {'vendor_order': vendor_order})
