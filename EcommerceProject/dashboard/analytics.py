"""Data for the Admin Dashboard overview.

Every number and chart on the overview is calculated here from the database. Money values
are returned as stored or summed; templates format them with the `money` filter, so the
calculations themselves are never rounded.
"""
from datetime import date, datetime, time, timedelta

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from accounts.models import User
from catalog.models import Product, ProductVariant
from catalog.money import format_money
from orders.models import Order, OrderItem, VendorOrder
from vendors.models import VendorStore

# Sub-orders in these states earn nothing. Same rule as the Reports and Commissions pages.
DEAD_STATUSES = ['cancelled', 'returned', 'refunded']
LOW_STOCK_THRESHOLD = 5          # variants with 1 to 5 units left count as low stock
RECENT_ORDER_COUNT = 10
CHART_RANGES = [('30d', 'Last 30 days'), ('12m', 'Last 12 months')]
DEFAULT_RANGE = '30d'
RANGE_KEYS = {key for key, _ in CHART_RANGES}
MIN_BAR_PCT = 2                  # a non-zero bar is never drawn shorter than this


def _pct(value, peak):
    if not value or not peak:
        return 0
    return max(MIN_BAR_PCT, round(float(value) * 100 / float(peak), 1))


def _bars(rows, key='count'):
    """Adds 'pct' (0-100, scaled to the largest row) to each row. Returns the same list."""
    peak = max((row[key] for row in rows), default=0)
    for row in rows:
        row['pct'] = _pct(row[key], peak)
    return rows


def _status_rows(queryset, field, choices):
    """One row per choice, including choices with no records, in the order they are declared."""
    counted = {row[field]: row['n'] for row in queryset.values(field).annotate(n=Count('pk'))}
    rows = [{'label': label, 'count': counted.get(value, 0)} for value, label in choices]
    return _bars(rows), sum(row['count'] for row in rows)


def _month_start(day, offset):
    index = day.year * 12 + (day.month - 1) + offset
    return date(index // 12, index % 12 + 1, 1)


def _chart_slots(range_key, today):
    """Zero-filled time slots for the order charts: 30 days (daily) or 12 months (monthly)."""
    if range_key == '12m':
        months = [_month_start(today, offset) for offset in range(-11, 1)]
        slots = [{'key': (m.year, m.month), 'label': m.strftime('%b'), 'show_label': True,
                  'full': m.strftime('%B %Y')} for m in months]
        bucket, start, period = TruncMonth('created_at'), months[0], 'month'
    else:
        days = [today - timedelta(days=n) for n in range(29, -1, -1)]
        slots = [{'key': d, 'label': d.strftime('%d %b'), 'show_label': i % 5 == 0 or i == len(days) - 1,
                  'full': d.strftime('%d %b %Y')} for i, d in enumerate(days)]
        bucket, start, period = TruncDate('created_at'), days[0], 'day'

    rows = (Order.objects.filter(created_at__gte=timezone.make_aware(datetime.combine(start, time.min)))
            .annotate(bucket=bucket).values('bucket')
            .annotate(orders=Count('pk'), sales=Sum('total_amount')))
    totals = {}
    for row in rows:
        key = (row['bucket'].year, row['bucket'].month) if range_key == '12m' else row['bucket']
        totals[key] = row
    for slot in slots:
        found = totals.get(slot['key'], {})
        slot['orders'] = found.get('orders', 0)
        slot['sales'] = found.get('sales') or 0
    return slots, period


def _charts(slots, period):
    """Two bar charts (sales, orders) built from the same slots."""
    peak_sales = max((s['sales'] for s in slots), default=0)
    peak_orders = max((s['orders'] for s in slots), default=0)
    sales_bars, orders_bars = [], []
    for s in slots:
        sales_bars.append({
            'label': s['label'], 'show_label': s['show_label'], 'pct': _pct(s['sales'], peak_sales),
            'title': f"{s['full']}: ₹{format_money(s['sales'])} from {s['orders']} order"
                     f"{'' if s['orders'] == 1 else 's'}",
        })
        orders_bars.append({
            'label': s['label'], 'show_label': s['show_label'], 'pct': _pct(s['orders'], peak_orders),
            'title': f"{s['full']}: {s['orders']} order{'' if s['orders'] == 1 else 's'}",
        })
    has_data = any(s['orders'] for s in slots)
    sales_chart = {'bars': sales_bars, 'has_data': has_data, 'period': period,
                   'total': sum((s['sales'] for s in slots), 0)}
    orders_chart = {'bars': orders_bars, 'has_data': has_data, 'period': period,
                    'total': sum(s['orders'] for s in slots)}
    return sales_chart, orders_chart


def overview(range_key):
    today = timezone.localdate()
    # The "last 30 days" figures start at local midnight 29 days ago, the same first day the
    # 30-day chart shows, so the cards and the chart always count the same orders.
    since_30_days = timezone.make_aware(datetime.combine(today - timedelta(days=29), time.min))

    # Vendors and approvals
    vendor_rows, _ = _status_rows(VendorStore.objects.all(), 'status', VendorStore.Status.choices)
    pending_vendors = VendorStore.objects.filter(status=VendorStore.Status.PENDING).count()
    approved_vendors = VendorStore.objects.filter(
        status__in=[VendorStore.Status.APPROVED, VendorStore.Status.ACTIVE]).count()

    # Customers
    total_customers = User.objects.filter(role=User.Role.CUSTOMER).count()
    new_customers_30d = User.objects.filter(role=User.Role.CUSTOMER, date_joined__gte=since_30_days).count()

    # Products and availability (availability looks at sellable variants: active product, active variant)
    product_rows, _ = _status_rows(Product.objects.all(), 'status', Product.Status.choices)
    total_products = Product.objects.count()
    active_products = Product.objects.filter(status=Product.Status.ACTIVE).count()
    pending_products = Product.objects.filter(status=Product.Status.PENDING).count()
    sellable = ProductVariant.objects.filter(is_active=True, product__status=Product.Status.ACTIVE)
    availability_rows = _bars([
        {'label': 'In stock', 'count': sellable.filter(stock_quantity__gt=LOW_STOCK_THRESHOLD).count()},
        {'label': f'Low stock (1-{LOW_STOCK_THRESHOLD})',
         'count': sellable.filter(stock_quantity__gte=1, stock_quantity__lte=LOW_STOCK_THRESHOLD).count()},
        {'label': 'Out of stock', 'count': sellable.filter(stock_quantity=0).count()},
    ])
    availability_total = sum(row['count'] for row in availability_rows)

    # Orders and sales. "Sales" is the gross total of every customer order, as before.
    order_totals = Order.objects.aggregate(total=Sum('total_amount'), count=Count('pk'))
    total_orders = order_totals['count']
    total_sales = order_totals['total'] or 0
    avg_order_value = total_sales / total_orders if total_orders else 0
    orders_30d = Order.objects.filter(created_at__gte=since_30_days).count()

    order_status_rows, order_status_total = _status_rows(VendorOrder.objects.all(), 'status',
                                                         VendorOrder.Status.choices)
    payment_by_status = {row['payment_status']: row for row in
                         Order.objects.values('payment_status').annotate(n=Count('pk'), amount=Sum('total_amount'))}
    payment_rows = [{'label': label,
                     'count': payment_by_status.get(value, {}).get('n', 0),
                     'amount': payment_by_status.get(value, {}).get('amount') or 0}
                    for value, label in Order.PaymentStatus.choices]

    # Commission: cancelled, returned and refunded sub-orders earn nothing (matches the Commissions page).
    commission_total = (VendorOrder.objects.exclude(status__in=DEAD_STATUSES)
                        .aggregate(total=Sum('commission_amount'))['total'] or 0)

    # Category performance: revenue from live sub-orders, grouped by the product's category.
    line_total = ExpressionWrapper(F('price') * F('quantity'), output_field=DecimalField(max_digits=14, decimal_places=2))
    category_rows = [
        {'label': row['variant__product__category__name'] or 'Uncategorised', 'value': row['revenue'] or 0}
        for row in (OrderItem.objects.exclude(vendor_order__status__in=DEAD_STATUSES)
                    .values('variant__product__category__name')
                    .annotate(revenue=Sum(line_total))
                    .order_by('-revenue')[:6])
    ]
    _bars(category_rows, 'value')

    slots, period = _chart_slots(range_key, today)
    sales_chart, orders_chart = _charts(slots, period)

    recent_orders = (Order.objects.select_related('customer').prefetch_related('vendor_orders')
                     .order_by('-created_at')[:RECENT_ORDER_COUNT])

    return {
        'range_key': range_key,
        'range_options': CHART_RANGES,
        'total_vendors': sum(row['count'] for row in vendor_rows),
        'approved_vendors': approved_vendors,
        'pending_vendors': pending_vendors,
        'total_customers': total_customers,
        'new_customers_30d': new_customers_30d,
        'total_products': total_products,
        'active_products': active_products,
        'pending_products': pending_products,
        'total_orders': total_orders,
        'orders_30d': orders_30d,
        'total_sales': total_sales,
        'avg_order_value': avg_order_value,
        'total_commission': commission_total,
        'vendor_status_rows': vendor_rows,
        'product_status_rows': product_rows,
        'product_status_total': sum(row['count'] for row in product_rows),
        'availability_rows': availability_rows,
        'availability_total': availability_total,
        'order_status_rows': order_status_rows,
        'order_status_total': order_status_total,
        'payment_rows': payment_rows,
        'category_rows': category_rows,
        'sales_chart': sales_chart,
        'orders_chart': orders_chart,
        'recent_orders': recent_orders,
    }
