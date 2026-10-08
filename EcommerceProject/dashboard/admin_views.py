"""Custom Admin Dashboard management pages (Categories, Brands, Coupons, Returns,
Refunds, Commissions).

These are the project's own pages, separate from Django Admin. Every view is wrapped
in `admin_required` (Admin or Super Admin role; anonymous -> login, Customer/Vendor
-> 403) and every state-changing view is POST-only with CSRF.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from accounts.models import User
from catalog.models import Brand, Category
from orders.models import Coupon, Order, VendorOrder
from returns_app.models import Refund, ReturnRequest

from .forms import BrandForm, CategoryForm, CouponAdminForm
from .views import admin_required, back_or as _back

PAGE_SIZE = 15


# ---------- helpers ------------------------------------------------------------------

def _paginate(request, queryset):
    """-> (page, querystring-without-page) so filters survive page changes."""
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return page, params.urlencode()


def _form_page(request, *, form_class, instance, active, noun, list_url):
    """Create/edit page shared by Categories, Brands and Coupons."""
    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save()
            verb = 'updated' if instance else 'created'
            messages.success(request, f'{noun} "{obj}" {verb}.')
            return redirect(list_url)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = form_class(instance=instance)
    return render(request, 'dashboard/manage/form.html', {
        'active': active, 'form': form, 'noun': noun, 'object': instance, 'list_url': list_url,
    })


# ---------- Categories ---------------------------------------------------------------

@admin_required
@require_safe
def category_list(request):
    q = request.GET.get('q', '').strip()
    categories = (Category.objects.select_related('parent')
                  .annotate(product_count=Count('products', distinct=True),
                            sub_count=Count('subcategories', distinct=True))
                  .order_by('name'))
    if q:
        categories = categories.filter(name__icontains=q)
    page, qs = _paginate(request, categories)
    return render(request, 'dashboard/manage/category_list.html',
                  {'active': 'categories', 'page_obj': page, 'qs': qs, 'q': q})


@admin_required
def category_add(request):
    return _form_page(request, form_class=CategoryForm, instance=None, active='categories',
                      noun='Category', list_url='dashboard:admin_categories')


@admin_required
def category_edit(request, pk):
    return _form_page(request, form_class=CategoryForm, instance=get_object_or_404(Category, pk=pk),
                      active='categories', noun='Category', list_url='dashboard:admin_categories')


@admin_required
@require_POST
def category_toggle(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save()
    messages.success(request, f'Category "{category}" {"activated" if category.is_active else "deactivated"}.')
    return _back(request, 'dashboard:admin_categories')


@admin_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    # Deleting would silently un-categorise products and cascade-delete sub-categories.
    if category.products.exists() or category.subcategories.exists():
        messages.error(request, f'"{category}" still has products or sub-categories. Deactivate it instead, or move them first.')
    else:
        category.delete()
        messages.success(request, f'Category "{category}" deleted.')
    return _back(request, 'dashboard:admin_categories')


# ---------- Brands -------------------------------------------------------------------

@admin_required
@require_safe
def brand_list(request):
    q = request.GET.get('q', '').strip()
    brands = Brand.objects.annotate(product_count=Count('products', distinct=True)).order_by('name')
    if q:
        brands = brands.filter(name__icontains=q)
    page, qs = _paginate(request, brands)
    return render(request, 'dashboard/manage/brand_list.html',
                  {'active': 'brands', 'page_obj': page, 'qs': qs, 'q': q})


@admin_required
def brand_add(request):
    return _form_page(request, form_class=BrandForm, instance=None, active='brands',
                      noun='Brand', list_url='dashboard:admin_brands')


@admin_required
def brand_edit(request, pk):
    return _form_page(request, form_class=BrandForm, instance=get_object_or_404(Brand, pk=pk),
                      active='brands', noun='Brand', list_url='dashboard:admin_brands')


@admin_required
@require_POST
def brand_toggle(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    brand.is_active = not brand.is_active
    brand.save()
    messages.success(request, f'Brand "{brand}" {"activated" if brand.is_active else "deactivated"}.')
    return _back(request, 'dashboard:admin_brands')


@admin_required
@require_POST
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if brand.products.exists():
        messages.error(request, f'"{brand}" is used by products. Deactivate it instead.')
    else:
        brand.delete()
        messages.success(request, f'Brand "{brand}" deleted.')
    return _back(request, 'dashboard:admin_brands')


# ---------- Coupons ------------------------------------------------------------------

COUPON_STATES = [('active', 'Active now'), ('scheduled', 'Scheduled'), ('expired', 'Expired'), ('inactive', 'Switched off')]


@admin_required
@require_safe
def coupon_list(request):
    q = request.GET.get('q', '').strip()
    state = request.GET.get('state', '')
    now = timezone.now()
    coupons = Coupon.objects.order_by('-expiry_date')
    if q:
        coupons = coupons.filter(code__icontains=q)
    if state == 'active':
        coupons = coupons.filter(is_active=True, start_date__lte=now, expiry_date__gte=now)
    elif state == 'scheduled':
        coupons = coupons.filter(is_active=True, start_date__gt=now)
    elif state == 'expired':
        coupons = coupons.filter(expiry_date__lt=now)
    elif state == 'inactive':
        coupons = coupons.filter(is_active=False)
    page, qs = _paginate(request, coupons)
    return render(request, 'dashboard/manage/coupon_list.html', {
        'active': 'coupons', 'page_obj': page, 'qs': qs, 'q': q, 'state': state,
        'states': COUPON_STATES, 'now': now,
    })


@admin_required
def coupon_add(request):
    return _form_page(request, form_class=CouponAdminForm, instance=None, active='coupons',
                      noun='Coupon', list_url='dashboard:admin_coupons')


@admin_required
def coupon_edit(request, pk):
    return _form_page(request, form_class=CouponAdminForm, instance=get_object_or_404(Coupon, pk=pk),
                      active='coupons', noun='Coupon', list_url='dashboard:admin_coupons')


@admin_required
@require_POST
def coupon_toggle(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    coupon.is_active = not coupon.is_active
    coupon.save()
    messages.success(request, f'Coupon {coupon.code} {"switched on" if coupon.is_active else "switched off"}.')
    return _back(request, 'dashboard:admin_coupons')


@admin_required
@require_POST
def coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    # Keep coupons that customers have used, so past orders still show which coupon applied.
    if coupon.used_count or Order.objects.filter(coupon=coupon).exists():
        messages.error(request, f'Coupon {coupon.code} has been used on orders. Switch it off instead of deleting it.')
    else:
        coupon.delete()
        messages.success(request, f'Coupon {coupon.code} deleted.')
    return _back(request, 'dashboard:admin_coupons')


# ---------- Returns ------------------------------------------------------------------

RS = ReturnRequest.Status
# status -> statuses an admin may move it to. Refunded is reached only by completing a refund.
RETURN_TRANSITIONS = {
    RS.REQUESTED.value: [RS.UNDER_REVIEW, RS.APPROVED, RS.REJECTED],
    RS.UNDER_REVIEW.value: [RS.APPROVED, RS.REJECTED],
    RS.APPROVED.value: [RS.RETURNED],
    RS.RETURNED.value: [],
    RS.REJECTED.value: [],
    RS.REFUNDED.value: [],
}


def _return_next_actions(return_request):
    allowed = RETURN_TRANSITIONS.get(return_request.status, [])
    return [(s.value, s.label) for s in allowed]


@admin_required
@require_safe
def return_list(request):
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    returns = (ReturnRequest.objects
               .select_related('customer', 'refund', 'order_item__vendor_order__vendor',
                               'order_item__vendor_order__order')
               .order_by('-created_at'))
    if status in RS.values:
        returns = returns.filter(status=status)
    if q:
        returns = returns.filter(Q(order_item__product_name__icontains=q)
                                 | Q(customer__username__icontains=q)
                                 | Q(order_item__vendor_order__order__order_number__icontains=q))
    page, qs = _paginate(request, returns)
    for r in page:
        r.next_actions = _return_next_actions(r)
        r.can_refund = r.status == RS.RETURNED and not hasattr(r, 'refund')
    return render(request, 'dashboard/manage/return_list.html', {
        'active': 'returns', 'page_obj': page, 'qs': qs, 'q': q, 'status': status,
        'statuses': RS.choices,
    })


@admin_required
@require_POST
def return_update(request, pk):
    with transaction.atomic():
        return_request = get_object_or_404(ReturnRequest.objects.select_for_update(), pk=pk)
        new_status = request.POST.get('status', '')
        if new_status in dict(_return_next_actions(return_request)):
            return_request.status = new_status
            return_request.save()
            messages.success(request, f'Return #{return_request.pk} marked "{return_request.get_status_display()}".')
        else:
            messages.error(request, 'That status change is not allowed.')
    return _back(request, 'dashboard:admin_returns')


@admin_required
@require_POST
def return_refund_create(request, pk):
    """Open a refund for a returned item. The amount is computed here, never posted."""
    with transaction.atomic():
        return_request = get_object_or_404(
            ReturnRequest.objects.select_for_update().select_related('order_item'), pk=pk)
        if return_request.status != RS.RETURNED:
            messages.error(request, 'A refund can only be opened once the product has been returned.')
        elif Refund.objects.filter(return_request=return_request).exists():
            messages.error(request, 'A refund already exists for this return.')
        else:
            amount = return_request.order_item.price * return_request.quantity
            Refund.objects.create(return_request=return_request, amount=amount)
            messages.success(request, f'Refund of ₹{amount} opened for return #{return_request.pk}.')
    return _back(request, 'dashboard:admin_returns')


# ---------- Refunds ------------------------------------------------------------------

FS = Refund.Status
REFUND_TRANSITIONS = {
    FS.PENDING.value: [FS.PROCESSING, FS.COMPLETED, FS.FAILED],
    FS.PROCESSING.value: [FS.COMPLETED, FS.FAILED],
    FS.FAILED.value: [FS.PROCESSING],
    FS.COMPLETED.value: [],
}


@admin_required
@require_safe
def refund_list(request):
    status = request.GET.get('status', '')
    refunds = (Refund.objects
               .select_related('return_request__customer', 'return_request__order_item__vendor_order__order')
               .order_by('-pk'))
    if status in FS.values:
        refunds = refunds.filter(status=status)
    totals = refunds.aggregate(total=Sum('amount'))
    page, qs = _paginate(request, refunds)
    for r in page:
        r.next_actions = [(s.value, s.label) for s in REFUND_TRANSITIONS.get(r.status, [])]
    return render(request, 'dashboard/manage/refund_list.html', {
        'active': 'refunds', 'page_obj': page, 'qs': qs, 'status': status,
        'statuses': FS.choices, 'total_amount': totals['total'] or 0,
    })


@admin_required
@require_POST
def refund_update(request, pk):
    with transaction.atomic():
        refund = get_object_or_404(Refund.objects.select_for_update().select_related('return_request'), pk=pk)
        new_status = request.POST.get('status', '')
        allowed = {s.value for s in REFUND_TRANSITIONS.get(refund.status, [])}
        if new_status not in allowed:
            messages.error(request, 'That status change is not allowed.')
        else:
            refund.status = new_status
            if new_status == FS.COMPLETED:
                refund.processed_at = timezone.now()
                # Money has gone back: the return itself is now finished.
                refund.return_request.status = RS.REFUNDED
                refund.return_request.save()
            refund.save()
            messages.success(request, f'Refund #{refund.pk} marked "{refund.get_status_display()}".')
    return _back(request, 'dashboard:admin_refunds')


# ---------- Commissions (read-only) ----------------------------------------------------

@admin_required
@require_safe
def commission_list(request):
    status = request.GET.get('status', '')
    vendor_id = request.GET.get('vendor', '')
    q = request.GET.get('q', '').strip()
    vendor_orders = (VendorOrder.objects
                     .select_related('order', 'vendor', 'vendor__store')
                     .order_by('-created_at'))
    if status in VendorOrder.Status.values:
        vendor_orders = vendor_orders.filter(status=status)
    if vendor_id.isdigit():
        vendor_orders = vendor_orders.filter(vendor_id=int(vendor_id))
    if q:
        vendor_orders = vendor_orders.filter(order__order_number__icontains=q)
    # Same rule as the vendor's own dashboard: cancelled/returned/refunded orders earn nothing.
    live = vendor_orders.exclude(status__in=['cancelled', 'returned', 'refunded'])
    totals = live.aggregate(sales=Sum('subtotal'), commission=Sum('commission_amount'),
                            earnings=Sum('vendor_earning'), count=Count('pk'))
    page, qs = _paginate(request, vendor_orders)
    return render(request, 'dashboard/manage/commission_list.html', {
        'active': 'commissions', 'page_obj': page, 'qs': qs, 'q': q, 'status': status,
        'vendor_id': vendor_id, 'statuses': VendorOrder.Status.choices,
        'vendors': User.objects.filter(role=User.Role.VENDOR).select_related('store').order_by('username'),
        'totals': {k: (v or 0) for k, v in totals.items()},
    })
