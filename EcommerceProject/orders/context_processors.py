def cart_summary(request):
    count = 0
    if request.user.is_authenticated:
        cart = getattr(request.user,'cart', None)
        if cart:
            count = cart.total_items()
    return {'cart_item_count':count}
