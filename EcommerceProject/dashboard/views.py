from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Count
from django.core.exceptions import PermissionDenied

from vendors.models import VendorStore
from catalog.models import Product
from orders.models import Order, VendorOrder
from accounts.models import User
# Create your views here.



def admin_required(view_func):
    def check(user):
        if user.is_authenticated and user.is_admin_role:
            return True
        raise PermissionDenied
    return user_passes_test(check)(view_func)


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
    orders = Order.objects.filter(customer=request.user).order_by('-created_at')
    context = {
        'recent_orders': orders[:5],
        'pending_orders': VendorOrder.objects.filter(
            order__customer=request.user
        ).exclude(status__in=['delivered', 'cancelled']).count(),
        'delivered_orders': VendorOrder.objects.filter(order__customer=request.user, status='delivered').count(),
        'wishlist_count': 0,  # wishlist not implemented in this starter — see README
        'saved_addresses': request.user.addresses.count(),
    }
    return render(request, 'dashboard/customer_dashboard.html', context)


@admin_required
def admin_dashboard(request):
    context = {
        'total_vendors': VendorStore.objects.count(),
        'pending_vendors': VendorStore.objects.filter(status=VendorStore.Status.PENDING).count(),
        'total_customers': User.objects.filter(role=User.Role.CUSTOMER).count(),
        'total_products': Product.objects.count(),
        'pending_products': Product.objects.filter(status=Product.Status.PENDING).count(),
        'total_orders': Order.objects.count(),
        'total_sales': Order.objects.aggregate(total=Sum('total_amount'))['total'] or 0,
        'total_commission': VendorOrder.objects.aggregate(total=Sum('commission_amount'))['total'] or 0,
        'recent_orders': Order.objects.order_by('-created_at')[:8],
        'pending_vendor_list': VendorStore.objects.filter(status=VendorStore.Status.PENDING),
        'pending_product_list': Product.objects.filter(status=Product.Status.PENDING)[:10],
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


@admin_required
def approve_vendor(request, pk):
    store = get_object_or_404(VendorStore, pk=pk)
    store.status = VendorStore.Status.APPROVED
    store.save()
    messages.success(request, f'{store.store_name} approved.')
    return redirect('dashboard:admin_dashboard')


@admin_required
def reject_vendor(request, pk):
    store = get_object_or_404(VendorStore, pk=pk)
    store.status = VendorStore.Status.REJECTED
    store.save()
    messages.success(request, f'{store.store_name} rejected.')
    return redirect('dashboard:admin_dashboard')


@admin_required
def approve_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.status = Product.Status.ACTIVE
    product.save()
    messages.success(request, f'{product.name} approved and made active.')
    return redirect('dashboard:admin_dashboard')


@admin_required
def reject_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.status = Product.Status.REJECTED
    product.save()
    messages.success(request, f'{product.name} rejected.')
    return redirect('dashboard:admin_dashboard')
