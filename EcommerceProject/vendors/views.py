from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum,Count
from .models import VendorStore
from django.core.exceptions import PermissionDenied
from .decorators import vendor_required,get_vendor_store,vendor_has_access
from .forms import VendorStoreForm
from catalog.models import Product,ProductVariant
from orders.models import VendorOrder

# Create your views here.

# Shown to a vendor who is signed in but not (yet) allowed to use vendor features.
ACCESS_MESSAGES={
    VendorStore.Status.PENDING:('Your store is awaiting approval',
        'Our team is reviewing your vendor registration. You will be able to manage products and orders once it is approved.'),
    VendorStore.Status.REJECTED:('Your vendor application was rejected',
        'Your store has not been approved, so vendor features are not available. Please contact support if you think this is a mistake.'),
    VendorStore.Status.INACTIVE:('Your store is inactive',
        'Your store has been deactivated, so vendor features are not available. Please contact support to have it re-enabled.'),
}

@login_required
def vendor_access_status(request):
    """Explains to a blocked vendor why vendor features are unavailable.
    Vendors with access go straight to their dashboard."""
    user=request.user
    if not user.is_vendor_role:
        raise PermissionDenied
    store=get_vendor_store(user)
    if vendor_has_access(user,store):
        return redirect('vendors:dashboard')
    if store is None:
        title,message='No vendor store found','No store is linked to your account. Please contact support.'
    elif not user.is_active_account:
        title,message='Your vendor account is deactivated','Vendor features are not available for this account. Please contact support.'
    else:
        title,message=ACCESS_MESSAGES.get(store.status,('Vendor access unavailable','Vendor features are not available for your store right now.'))
    return render(request,'vendors/access_status.html',{'store':store,'title':title,'message':message})

@vendor_required
def store_settings(request):
    store=get_object_or_404(VendorStore,vendor=request.user)
    if request.method=='POST':
        form=VendorStoreForm(request.POST,request.FILES,instance=store)
        if form.is_valid():
            form.save()
            messages.success(request,'Store details updated.')
            return redirect('vendors:store_settings')
    else:
        form=VendorStoreForm(instance=store)
    return render(request,'vendors/store_settings.html',{'form':form,'store':store})

@vendor_required
def vendor_dashboard(request):
    store=get_object_or_404(VendorStore,vendor=request.user)
    products=Product.objects.filter(vendor=request.user)

    context={
        'store':store,
        'total_products':products.count(),
        'low_stock_count':sum(1 for p in products if p.total_stock()<=5),
    }
    vos=VendorOrder.objects.filter(vendor=request.user)
    live=vos.exclude(status__in=['cancelled','returned','refunded'])
    agg=live.aggregate(s=Sum('subtotal'),c=Sum('commission_amount'),e=Sum('vendor_earning'))
    context.update({
        'total_orders':vos.count(),
        'pending_orders':vos.filter(status='pending').count(),
        'total_sales':agg['s'] or 0,
        'total_commission':agg['c'] or 0,
        'net_earnings':agg['e'] or 0,
        'recent_orders':vos.select_related('order').order_by('-created_at')[:8],
        'inventory':ProductVariant.objects.filter(product__vendor=request.user,is_active=True).select_related('product').order_by('stock_quantity')[:15],
    })
    return render(request,'vendors/dashboard.html',context)

def store_public_view(request,store_id):
    store=get_object_or_404(VendorStore,id=store_id)
    products=Product.objects.filter(vendor=store.vendor,status=Product.Status.ACTIVE)
    return render(request,'vendors/store_public.html',{'store':store,'products':products})