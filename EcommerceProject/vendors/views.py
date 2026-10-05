from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum,Count
from .models import VendorStore
from .decorators import vendor_required
from .forms import VendorStoreForm
from catalog.models import Product,ProductVariant
from orders.models import VendorOrder

# Create your views here.

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