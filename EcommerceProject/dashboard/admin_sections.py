"""Custom Admin Dashboard: Vendors, Customers, Products, Orders, Promotions, Reports, Settings.

Same rules as admin_views.py: every view is wrapped in `admin_required` (Admin or Super
Admin role) and state-changing views are POST-only with CSRF. Nothing here links to or
depends on Django Admin.
"""
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from accounts.models import User
from catalog.models import Product
from orders.models import Coupon, Order, OrderItem, VendorOrder
from returns_app.models import Refund
from vendors.models import VendorStore

from .admin_views import _paginate
from .views import admin_required, back_or as _back

DEAD_STATUSES = ['cancelled', 'returned', 'refunded']   # these earn nothing (same rule as the vendor dashboard)


# ---------- Vendors ------------------------------------------------------------------

# The statuses an admin can put a store into. Pending is only ever the starting state.
VENDOR_SETTABLE = [VendorStore.Status.APPROVED.value, VendorStore.Status.REJECTED.value,
                   VendorStore.Status.INACTIVE.value]


@admin_required
@require_safe
def vendor_list(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    stores = (VendorStore.objects.select_related('vendor')
              .annotate(product_count=Count('vendor__products', distinct=True),
                        order_count=Count('vendor__vendor_orders', distinct=True))
              .order_by('-registered_at'))
    if status in VendorStore.Status.values:
        stores = stores.filter(status=status)
    if q:
        stores = stores.filter(Q(store_name__icontains=q) | Q(vendor__username__icontains=q)
                               | Q(vendor__email__icontains=q))
    page, qs = _paginate(request, stores)
    return render(request, 'dashboard/manage/vendor_list.html', {
        'active': 'vendors', 'page_obj': page, 'qs': qs, 'q': q, 'status': status,
        'statuses': VendorStore.Status.choices,
    })


@admin_required
@require_POST
def vendor_set_status(request, pk):
    store = get_object_or_404(VendorStore, pk=pk)
    new_status = request.POST.get('status', '')
    if new_status not in VENDOR_SETTABLE:
        messages.error(request, 'That status change is not allowed.')
    else:
        store.status = new_status
        store.save()
        messages.success(request, f'{store.store_name} is now "{store.get_status_display()}".')
    return _back(request, 'dashboard:admin_vendors')


# ---------- Customers ----------------------------------------------------------------

@admin_required
@require_safe
def customer_list(request):
    q = request.GET.get('q', '').strip()
    state = request.GET.get('state', '')
    customers = (User.objects.filter(role=User.Role.CUSTOMER)
                 .annotate(order_count=Count('orders', distinct=True), spent=Sum('orders__total_amount'))
                 .order_by('-date_joined'))
    if state == 'active':
        customers = customers.filter(is_active=True)
    elif state == 'blocked':
        customers = customers.filter(is_active=False)
    if q:
        customers = customers.filter(Q(username__icontains=q) | Q(email__icontains=q)
                                     | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    page, qs = _paginate(request, customers)
    return render(request, 'dashboard/manage/customer_list.html', {
        'active': 'customers', 'page_obj': page, 'qs': qs, 'q': q, 'state': state,
    })


@admin_required
@require_POST
def customer_toggle(request, pk):
    """Block / unblock a customer's login. Only ever acts on Customer-role accounts."""
    customer = get_object_or_404(User, pk=pk, role=User.Role.CUSTOMER)
    customer.is_active = not customer.is_active
    customer.save()
    messages.success(request, f'{customer.username} {"unblocked" if customer.is_active else "blocked"}.')
    return _back(request, 'dashboard:admin_customers')


# ---------- Products -----------------------------------------------------------------

PRODUCT_SETTABLE = [Product.Status.ACTIVE.value, Product.Status.INACTIVE.value, Product.Status.REJECTED.value]


@admin_required
@require_safe
def product_list(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    products = Product.objects.select_related('vendor', 'category', 'brand').order_by('-created_at')
    if status in Product.Status.values:
        products = products.filter(status=status)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(vendor__username__icontains=q))
    page, qs = _paginate(request, products)
    return render(request, 'dashboard/manage/product_list.html', {
        'active': 'products', 'page_obj': page, 'qs': qs, 'q': q, 'status': status,
        'statuses': Product.Status.choices,
    })


@admin_required
@require_POST
def product_set_status(request, pk):
    product = get_object_or_404(Product, pk=pk)
    new_status = request.POST.get('status', '')
    if new_status not in PRODUCT_SETTABLE:
        messages.error(request, 'That status change is not allowed.')
    else:
        product.status = new_status
        product.save()
        messages.success(request, f'"{product.name}" is now "{product.get_status_display()}".')
    return _back(request, 'dashboard:admin_products')


# ---------- Orders (read-only) ---------------------------------------------------------

@admin_required
@require_safe
def order_list(request):
    q = request.GET.get('q', '').strip()
    payment = request.GET.get('payment', '')
    orders = (Order.objects.select_related('customer')
              .annotate(vendor_count=Count('vendor_orders', distinct=True))
              .order_by('-created_at'))
    if payment in Order.PaymentStatus.values:
        orders = orders.filter(payment_status=payment)
    if q:
        orders = orders.filter(Q(order_number__icontains=q) | Q(customer__username__icontains=q))
    page, qs = _paginate(request, orders)
    return render(request, 'dashboard/manage/order_list.html', {
        'active': 'orders', 'page_obj': page, 'qs': qs, 'q': q, 'payment': payment,
        'payment_statuses': Order.PaymentStatus.choices,
    })


@admin_required
@require_safe
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('customer', 'shipping_address'), pk=pk)
    vendor_orders = (VendorOrder.objects.filter(order=order)
                     .select_related('vendor', 'vendor__store').prefetch_related('items').order_by('pk'))
    return render(request, 'dashboard/manage/order_detail.html', {
        'active': 'orders', 'order': order, 'vendor_orders': vendor_orders,
    })


# ---------- Promotions (built on coupons) ------------------------------------------------

@admin_required
@require_safe
def promotions(request):
    """Which promotions are running, coming up, ending soon, or recently over."""
    now = timezone.now()
    soon = now + timedelta(days=7)
    running = Coupon.objects.filter(is_active=True, start_date__lte=now, expiry_date__gte=now)
    context = {
        'active': 'promotions',
        'running': running.order_by('expiry_date')[:10],
        'running_count': running.count(),
        'ending_soon': running.filter(expiry_date__lte=soon).order_by('expiry_date')[:10],
        'scheduled': Coupon.objects.filter(is_active=True, start_date__gt=now).order_by('start_date')[:10],
        'scheduled_count': Coupon.objects.filter(is_active=True, start_date__gt=now).count(),
        'recently_ended': Coupon.objects.filter(expiry_date__lt=now, expiry_date__gte=now - timedelta(days=30))
                                        .order_by('-expiry_date')[:10],
        'switched_off_count': Coupon.objects.filter(is_active=False).count(),
        'coupon_uses': Coupon.objects.aggregate(n=Sum('used_count'))['n'] or 0,
    }
    return render(request, 'dashboard/manage/promotions.html', context)


# ---------- Reports (read-only) --------------------------------------------------------

REPORT_RANGES = [('7', 'Last 7 days'), ('30', 'Last 30 days'), ('90', 'Last 90 days'), ('all', 'All time')]


@admin_required
@require_safe
def reports(request):
    chosen = request.GET.get('range', '30')
    if chosen not in dict(REPORT_RANGES):
        chosen = '30'
    since = None if chosen == 'all' else timezone.now() - timedelta(days=int(chosen))

    def within(qs, field='created_at'):
        return qs if since is None else qs.filter(**{f'{field}__gte': since})

    orders = within(Order.objects.all())
    live = within(VendorOrder.objects.exclude(status__in=DEAD_STATUSES))
    money = live.aggregate(sales=Sum('subtotal'), commission=Sum('commission_amount'),
                           earnings=Sum('vendor_earning'))
    refunded = within(Refund.objects.filter(status=Refund.Status.COMPLETED), 'processed_at').aggregate(n=Sum('amount'))['n']

    status_labels = dict(VendorOrder.Status.choices)
    by_status = [{'label': status_labels.get(row['status'], row['status']), 'status': row['status'], 'count': row['count']}
                 for row in within(VendorOrder.objects.all()).values('status').annotate(count=Count('pk')).order_by('-count')]

    top_vendors = (live.values('vendor__username', 'vendor__store__store_name')
                   .annotate(sales=Sum('subtotal'), commission=Sum('commission_amount'), orders=Count('pk'))
                   .order_by('-sales')[:5])
    line_total = ExpressionWrapper(F('price') * F('quantity'), output_field=DecimalField(max_digits=14, decimal_places=2))
    items = within(OrderItem.objects.exclude(vendor_order__status__in=DEAD_STATUSES), 'vendor_order__created_at')
    top_products = (items.values('product_name').annotate(units=Sum('quantity'), revenue=Sum(line_total))
                    .order_by('-units', 'product_name')[:5])

    return render(request, 'dashboard/manage/reports.html', {
        'active': 'reports', 'ranges': REPORT_RANGES, 'chosen': chosen,
        'order_count': orders.count(),
        'gross_sales': orders.aggregate(n=Sum('total_amount'))['n'] or 0,
        'sales': money['sales'] or 0, 'commission': money['commission'] or 0, 'earnings': money['earnings'] or 0,
        'refunded': refunded or 0,
        'new_customers': within(User.objects.filter(role=User.Role.CUSTOMER), 'date_joined').count(),
        'new_vendors': within(VendorStore.objects.all(), 'registered_at').count(),
        'by_status': by_status, 'top_vendors': top_vendors, 'top_products': top_products,
    })


# ---------- Settings (read-only) -------------------------------------------------------

@admin_required
@require_safe
def settings_page(request):
    """Shows how the platform is currently configured. These values live in the code
    (orders/views.py), so this page is informational: it never edits anything."""
    from orders.views import (DEFAULT_COMMISSION_PERCENT, FREE_SHIPPING_THRESHOLD,
                              SHIPPING_FLAT_CHARGE, TAX_PERCENT)
    role_counts = {row['role']: row['n'] for row in User.objects.values('role').annotate(n=Count('pk'))}
    return render(request, 'dashboard/manage/settings.html', {
        'active': 'settings',
        'config': [
            ('Default vendor commission', f'{DEFAULT_COMMISSION_PERCENT}%', 'Applied to each vendor order when it is placed.'),
            ('Tax', f'{TAX_PERCENT}%', 'Added to the taxable amount at checkout.'),
            ('Flat shipping charge', f'₹{SHIPPING_FLAT_CHARGE}', 'Charged on orders below the free-shipping threshold.'),
            ('Free shipping from', f'₹{FREE_SHIPPING_THRESHOLD}', 'Order subtotal at or above this ships free.'),
        ],
        'roles': [(label, role_counts.get(value, 0)) for value, label in User.Role.choices],
        'pending_vendors': VendorStore.objects.filter(status=VendorStore.Status.PENDING).count(),
        'pending_products': Product.objects.filter(status=Product.Status.PENDING).count(),
    })
