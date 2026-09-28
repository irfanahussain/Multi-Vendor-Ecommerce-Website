from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from catalog.models import Product
from orders.models import OrderItem
from .forms import ReviewForm
from .models import Review

# Create your views here.




@require_POST
@login_required
def add_review(request, product_id):
    product = get_object_or_404(Product,pk=product_id)

    purchased_and_delivered=OrderItem.objects.filter(
        vendor_order__order__customer=request.user,
        variant__product=product,
        vendor_order__status='delivered',
    ).exists()

    if not purchased_and_delivered:
        messages.error(request,"You can only review products you've purchased and received.")
        return redirect(product.get_absolute_url())

    if Review.objects.filter(product=product,customer=request.user).exists():
        messages.error(request, "You've already reviewed this product.")
        return redirect(product.get_absolute_url())

    form=ReviewForm(request.POST)
    if form.is_valid():
        review=form.save(commit=False)
        review.product=product
        review.customer=request.user
        review.save()
        messages.success(request,'Thanks for your review!')
    else:
        messages.error(request,'Please provide a valid rating.')
    return redirect(product.get_absolute_url())
