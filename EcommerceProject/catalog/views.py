from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q,Sum,F
from django.http import Http404
from django.core.paginator import Paginator
from .models import Product,Category,Brand,ProductVariant,StockHistory
from .forms import ProductForm,ProductVariantForm,StockAdjustForm
from vendors.decorators import vendor_required

def landing(request):
    from orders.views import FREE_SHIPPING_THRESHOLD
    active=Product.objects.filter(status=Product.Status.ACTIVE).select_related('vendor','category')
    best=list(active.annotate(sold=Sum('variants__orderitem__quantity')).order_by(F('sold').desc(nulls_last=True),'-created_at')[:12])
    def pct(p):
        d=p.discount_percent
        return d() if callable(d) else (d or 0)
    max_discount=max([pct(p) for p in active.filter(discount_price__isnull=False)[:100]] or [0])
    return render(request,'catalog/landing.html',{
        'categories':Category.objects.filter(is_active=True,parent=None)[:7],
        'best_sellers':best,
        'hero_product':best[0] if best else None,
        'max_discount':max_discount,
        'free_shipping':FREE_SHIPPING_THRESHOLD,
    })

def home(request):
    products=Product.objects.filter(status=Product.Status.ACTIVE)
    query=request.GET.get('q','')
    category_slug=request.GET.get('category','')
    brand_id=request.GET.get('brand','')
    min_price=request.GET.get('min_price','')
    max_price=request.GET.get('max_price','')
    sort=request.GET.get('sort','')
    if request.GET.get('deals'):
        products=products.filter(discount_price__isnull=False)
    if query:
        products=products.filter(Q(name__icontains=query)|Q(description__icontains=query))
    if category_slug:
        products=products.filter(category__slug=category_slug)
    if brand_id:
        products=products.filter(brand_id=brand_id)
    if min_price:
        products=products.filter(price__gte=min_price)
    if max_price:
        products=products.filter(price__lte=max_price)
    if sort=='price_low':
        products=products.order_by('price')
    elif sort=='price_high':
        products=products.order_by('-price')
    elif sort=='newest':
        products=products.order_by('-created_at')
    else:
        products=products.order_by('-created_at')
    paginator=Paginator(products,12)
    page_obj=paginator.get_page(request.GET.get('page'))
    context={
        'page_obj':page_obj,
        'categories':Category.objects.filter(is_active=True,parent=None),
        'brands':Brand.objects.filter(is_active=True),
        'query':query,
        'selected_category':category_slug,
        'selected_brand':brand_id,
        'sort':sort,
    }
    return render(request,'catalog/home.html',context)

def product_detail(request,slug):
    product=get_object_or_404(Product,slug=slug)
    u=request.user
    if product.status!=Product.Status.ACTIVE and not (u.is_authenticated and (u.is_admin_role or product.vendor_id==u.id)):
        raise Http404
    variants=product.variants.filter(is_active=True)
    related=Product.objects.filter(category=product.category,status=Product.Status.ACTIVE).exclude(pk=product.pk)[:4]
    reviews=product.reviews.filter(is_hidden=False).order_by('-created_at')
    can_review=False
    if request.user.is_authenticated and request.user.is_customer_role:
        from orders.models import OrderItem
        can_review=OrderItem.objects.filter(
            vendor_order__order__customer=request.user,
            variant__product=product,
            vendor_order__status='delivered',
        ).exists()
    context={
        'product':product,
        'variants':variants,
        'related':related,
        'reviews':reviews,
        'can_review':can_review,
    }
    return render(request,'catalog/product_detail.html',context)

@vendor_required
def vendor_product_list(request):
    products=Product.objects.filter(vendor=request.user).order_by('-created_at')
    return render(request,'catalog/vendor_product_list.html',{'products':products})

@vendor_required
def vendor_product_create(request):
    if request.method=='POST':
        form=ProductForm(request.POST,request.FILES)
        if form.is_valid():
            product=form.save(commit=False)
            product.vendor=request.user
            product.status=Product.Status.PENDING
            product.save()
            ProductVariant.objects.create(
                product=product,
                name='Default',
                sku=f"{product.sku}-DEF",
                price=None,
                stock_quantity=0,
            )
            messages.success(request,'Product submitted for admin approval.')
            return redirect('catalog:vendor_product_variants',pk=product.pk)
    else:
        form=ProductForm()
    return render(request,'catalog/vendor_product_form.html',{'form':form})

@vendor_required
def vendor_product_edit(request,pk):
    product=get_object_or_404(Product,pk=pk,vendor=request.user)
    if request.method=='POST':
        form=ProductForm(request.POST,request.FILES,instance=product)
        if form.is_valid():
            form.save()
            messages.success(request,'Product updated.')
            return redirect('catalog:vendor_product_list')
    else:
        form=ProductForm(instance=product)
    return render(request,'catalog/vendor_product_form.html',{'form':form,'product':product})

@vendor_required
def vendor_product_variants(request,pk):
    product=get_object_or_404(Product,pk=pk,vendor=request.user)
    if request.method=='POST':
        form=ProductVariantForm(request.POST,request.FILES)
        if form.is_valid():
            variant=form.save(commit=False)
            variant.product=product
            variant.save()
            if variant.stock_quantity:
                StockHistory.objects.create(
                    variant=variant,
                    change_quantity=variant.stock_quantity,
                    reason=StockHistory.Reason.RESTOCK,
                    note='Initial stock',
                )
            messages.success(request,'Variant added.')
            return redirect('catalog:vendor_product_variants',pk=product.pk)
    else:
        form=ProductVariantForm()
    variants=product.variants.all()
    return render(request,'catalog/vendor_product_variants.html',{
        'product':product,
        'variants':variants,
        'form':form,
    })

@vendor_required
def vendor_variant_stock(request,pk):
    variant=get_object_or_404(ProductVariant,pk=pk,product__vendor=request.user)
    if request.method=='POST':
        form=StockAdjustForm(request.POST)
        if form.is_valid():
            change=form.cleaned_data['change_quantity']
            new_qty=variant.stock_quantity+change
            if new_qty<0:
                messages.error(request,"Stock can't go below zero.")
            else:
                variant.stock_quantity=new_qty
                variant.save()
                StockHistory.objects.create(
                    variant=variant,
                    change_quantity=change,
                    reason=StockHistory.Reason.ADJUSTMENT,
                    note=form.cleaned_data.get('note',''),
                )
                messages.success(request,'Stock updated.')
            return redirect('catalog:vendor_product_variants',pk=variant.product.pk)
    else:
        form=StockAdjustForm()
    return render(request,'catalog/vendor_variant_stock.html',{'variant':variant,'form':form})