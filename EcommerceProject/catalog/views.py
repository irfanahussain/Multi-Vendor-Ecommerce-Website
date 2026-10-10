from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decimal import Decimal,InvalidOperation
from django.db.models import Q,Sum,F,Prefetch
from django.http import Http404
from django.core.paginator import Paginator
from .models import Product,Category,Brand,ProductVariant,StockHistory
from .forms import ProductForm,ProductVariantForm,StockAdjustForm
from vendors.decorators import vendor_required
from wishlist.utils import wishlisted_ids

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

def category_tree_ids(category):
    """The category's own id plus the ids of all its sub-categories (any depth).

    A shopper who picks a parent category expects to see the products filed under its
    sub-categories too; filtering on the parent's slug alone hid them."""
    ids=[category.pk]
    frontier=[category.pk]
    while frontier:
        frontier=list(Category.objects.filter(parent_id__in=frontier).exclude(pk__in=ids).values_list('pk',flat=True))
        ids.extend(frontier)
    return ids

MAX_FILTER_PRICE=Decimal('99999999.99')

def _decimal_or_none(raw):
    """Parse a price filter. Garbage such as 'abc' is ignored instead of raising a 500."""
    try:
        value=Decimal(str(raw).strip())
    except (InvalidOperation,ValueError):
        return None
    if not value.is_finite() or value<0:
        return None
    # Price columns hold at most 8 whole digits (max_digits=10, decimal_places=2); a larger
    # number would make the database layer raise, so clamp it instead of returning a 500.
    return min(value,MAX_FILTER_PRICE)

def home(request):
    products=(Product.objects.filter(status=Product.Status.ACTIVE)
              .select_related('vendor','vendor__store','category').prefetch_related('variants'))
    query=request.GET.get('q','').strip()
    category_slug=request.GET.get('category','').strip()
    brand_id=request.GET.get('brand','').strip()
    min_price=_decimal_or_none(request.GET.get('min_price',''))
    max_price=_decimal_or_none(request.GET.get('max_price',''))
    sort=request.GET.get('sort','')
    deals=bool(request.GET.get('deals'))
    selected_category=None
    if deals:
        products=products.filter(discount_price__isnull=False)
    if query:
        products=products.filter(Q(name__icontains=query)|Q(description__icontains=query))
    if category_slug:
        selected_category=Category.objects.filter(slug=category_slug).first()
        if selected_category:
            products=products.filter(category_id__in=category_tree_ids(selected_category))
        else:
            products=products.none()
    if brand_id:
        if brand_id.isascii() and brand_id.isdigit() and len(brand_id)<=9:   # '²' or a 30-digit id would crash the query
            products=products.filter(brand_id=brand_id)
        else:
            products=products.none()
    if min_price is not None:
        products=products.filter(price__gte=min_price)
    if max_price is not None:
        products=products.filter(price__lte=max_price)
    if sort=='price_low':
        products=products.order_by('price','-created_at')
    elif sort=='price_high':
        products=products.order_by('-price','-created_at')
    else:
        products=products.order_by('-created_at')
    paginator=Paginator(products,12)
    page_obj=paginator.get_page(request.GET.get('page'))
    # Query string for the pagination links: everything except `page`, properly encoded.
    keep=request.GET.copy()
    keep.pop('page',None)
    context={
        'page_obj':page_obj,
        'result_count':paginator.count,
        'wishlist_ids':wishlisted_ids(request.user,[p.id for p in page_obj]),
        'categories':Category.objects.filter(is_active=True,parent=None).prefetch_related(
            Prefetch('subcategories',queryset=Category.objects.filter(is_active=True).order_by('name'))).order_by('name'),
        'brands':Brand.objects.filter(is_active=True).order_by('name'),
        'query':query,
        'selected_category':category_slug,
        'selected_category_obj':selected_category,
        'selected_brand':brand_id,
        'min_price':request.GET.get('min_price',''),
        'max_price':request.GET.get('max_price',''),
        'sort':sort,
        'deals':deals,
        'has_filters':bool(query or category_slug or brand_id or min_price is not None or max_price is not None or deals),
        'page_query':keep.urlencode(),
    }
    return render(request,'catalog/home.html',context)

def product_detail(request,slug):
    product=get_object_or_404(Product,slug=slug)
    u=request.user
    if product.status!=Product.Status.ACTIVE and not (u.is_authenticated and (u.is_admin_role or product.vendor_id==u.id)):
        raise Http404
    variants=sorted(product.variants.filter(is_active=True).order_by('id'),key=lambda v:v.stock_quantity==0)
    related=(Product.objects.filter(category=product.category,status=Product.Status.ACTIVE).exclude(pk=product.pk)
             .select_related('vendor','vendor__store') if product.category_id else Product.objects.none())[:4]
    reviews=list(product.reviews.filter(is_hidden=False).select_related('customer').order_by('-created_at'))
    can_review=False
    if request.user.is_authenticated and request.user.is_customer_role:
        from orders.models import OrderItem
        can_review=OrderItem.objects.filter(
            vendor_order__order__customer=request.user,
            variant__product=product,
            vendor_order__status='delivered',
        ).exists()
    gallery=[]
    for img,alt in [(product.image,product.name)]+[(v.image,v.name) for v in variants]:
        if img and img.url not in [g['url'] for g in gallery]:
            gallery.append({'url':img.url,'alt':alt})
    rating_counts=[{'stars':n,'count':sum(1 for r in reviews if r.rating==n)} for n in (5,4,3,2,1)]
    context={
        'product':product,
        'gallery':gallery,
        'avg_rating':product.average_rating(),
        'rating_counts':rating_counts,
        'variants':variants,
        'related':related,
        'reviews':reviews,
        'can_review':can_review,
        'wishlist_ids':wishlisted_ids(request.user,[product.id]+[p.id for p in related]),
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