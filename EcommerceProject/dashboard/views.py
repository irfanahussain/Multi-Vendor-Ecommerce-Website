from django.shortcuts import render, redirect, get_object_or_404
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.db.models import Sum, Count
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST, require_safe
from django.utils.http import url_has_allowed_host_and_scheme

from vendors.models import VendorStore
from catalog.models import Product
from orders.models import Order, VendorOrder
from accounts.models import User
from wishlist.models import Wishlist
# Create your views here.



def admin_required(view_func):
    """Admin Dashboard access: Admin or Super Admin roles only.
    anonymous -> login page; Customer / Vendor -> 403."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user.is_admin_role:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def back_or(request, default_name):
    """After a POST action: return to the page it came from (same host only), else `default_name`."""
    target = request.POST.get('next', '')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return redirect(target)
    return redirect(default_name)


@login_required
def redirect_by_role(request):
    """Sends a freshly logged-in user to the dashboard that matches their role."""
    user = request.user
    if user.is_admin_role:
        return redirect('dashboard:admin_dashboard')
    if user.is_vendor_role:
        return redirect('vendors:dashboard')
    return redirect('dashboard:customer_dashboard')


@login_required
def customer_dashboard(request):
    if not request.user.is_customer_role:
        # Vendors / Admins / Super Admins have their own dashboard.
        return redirect('dashboard:redirect')
    orders = Order.objects.filter(customer=request.user).order_by('-created_at')
    context = {
        'recent_orders': orders[:5],
        'pending_orders': VendorOrder.objects.filter(
            order__customer=request.user
        ).exclude(status__in=['delivered', 'cancelled']).count(),
        'delivered_orders': VendorOrder.objects.filter(order__customer=request.user, status='delivered').count(),
        'wishlist_count': Wishlist.objects.filter(user=request.user).count(),
        'saved_addresses': request.user.addresses.count(),
    }
    return render(request, 'dashboard/customer_dashboard.html', context)


@admin_required
@require_safe
def admin_dashboard(request):
    context = {
        'active': 'overview',
        'total_vendors': VendorStore.objects.count(),
        'pending_vendors': VendorStore.objects.filter(status=VendorStore.Status.PENDING).count(),
        'total_customers': User.objects.filter(role=User.Role.CUSTOMER).count(),
        'total_products': Product.objects.count(),
        'pending_products': Product.objects.filter(status=Product.Status.PENDING).count(),
        'total_orders': Order.objects.count(),
        'total_sales': Order.objects.aggregate(total=Sum('total_amount'))['total'] or 0,
        'total_commission': VendorOrder.objects.aggregate(total=Sum('commission_amount'))['total'] or 0,
        'recent_orders': Order.objects.select_related('customer').order_by('-created_at')[:8],
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


@admin_required
@require_safe
def admin_approvals(request):
    """Pending vendor stores and pending products, with approve / reject buttons."""
    context = {
        'active': 'approvals',
        'pending_vendor_list': VendorStore.objects.filter(status=VendorStore.Status.PENDING).select_related('vendor'),
        'pending_product_list': Product.objects.filter(status=Product.Status.PENDING).select_related('vendor')[:50],
    }
    return render(request, 'dashboard/admin_approvals.html', context)


# ---- Approve / reject actions -------------------------------------------------------
# Order of decorators matters: admin_required is outermost so that anonymous users
# are sent to login and Customers/Vendors get 403 *before* the method check; only a
# real Admin/Super Admin ever reaches require_POST (GET -> 405, state never changes).

@admin_required
@require_POST
def approve_vendor(request, pk):
    store = get_object_or_404(VendorStore, pk=pk)
    store.status = VendorStore.Status.APPROVED
    store.save()
    messages.success(request, f'{store.store_name} approved.')
    return back_or(request, 'dashboard:admin_approvals')


@admin_required
@require_POST
def reject_vendor(request, pk):
    store = get_object_or_404(VendorStore, pk=pk)
    store.status = VendorStore.Status.REJECTED
    store.save()
    messages.success(request, f'{store.store_name} rejected.')
    return back_or(request, 'dashboard:admin_approvals')


@admin_required
@require_POST
def approve_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.status = Product.Status.ACTIVE
    product.save()
    messages.success(request, f'{product.name} approved and made active.')
    return back_or(request, 'dashboard:admin_approvals')


@admin_required
@require_POST
def reject_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.status = Product.Status.REJECTED
    product.save()
    messages.success(request, f'{product.name} rejected.')
    return back_or(request, 'dashboard:admin_approvals')
