from .models import Wishlist


def wishlisted_ids(user, product_ids):
    """Return the set of product ids (from `product_ids`) in this user's wishlist.

    One query per page render, none for anonymous users / non-customers.
    """
    if not user.is_authenticated or not user.is_customer_role:
        return set()
    return set(
        Wishlist.objects.filter(user=user, product_id__in=list(product_ids))
        .values_list('product_id', flat=True)
    )
