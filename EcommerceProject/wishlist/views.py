from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Product, ProductVariant
from .decorators import customer_required, safe_next
from .models import Wishlist


def _back(request, product_id, fallback):
    """Redirect to the page the customer came from, keeping their place on a product grid."""
    target = safe_next(request, fallback)
    if '#' not in target and target != fallback:
        target = f"{target}#product-{product_id}"
    return redirect(target)


@customer_required
def wishlist_view(request):
    items = (
        Wishlist.objects.filter(user=request.user)
        .select_related('product', 'product__vendor', 'product__vendor__store')
        .prefetch_related(Prefetch(
            'product__variants',
            queryset=ProductVariant.objects.filter(is_active=True),
        ))
        .order_by('-created_at')
    )
    page_obj = Paginator(items, 24).get_page(request.GET.get('page'))
    return render(request, 'wishlist/wishlist.html', {
        'page_obj': page_obj,
        'active_status': Product.Status.ACTIVE,
    })


@customer_required
@require_POST
def wishlist_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, status=Product.Status.ACTIVE)
    _, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if created:
        messages.success(request, f"Added {product.name} to your wishlist.")
    else:
        messages.info(request, f"{product.name} is already in your wishlist.")
    return _back(request, product.pk, product.get_absolute_url())


@customer_required
@require_POST
def wishlist_remove(request, product_id):
    # Always scoped to the logged-in customer; works even if the product is now inactive.
    deleted, _ = Wishlist.objects.filter(user=request.user, product_id=product_id).delete()
    if deleted:
        messages.success(request, "Removed from your wishlist.")
    return _back(request, product_id, 'wishlist:list')
