from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import VendorStore


def get_vendor_store(user):
    """Return the user's VendorStore, or None if they have no store."""
    return VendorStore.objects.filter(vendor=user).first()


def vendor_has_access(user, store):
    """True only for a vendor-role user whose store is Approved/Active
    and whose account is not deactivated."""
    return bool(
        user.is_vendor_role
        and user.is_active_account
        and store is not None
        and store.is_active_store
    )


def vendor_required(view_func):
    """Restrict a view to approved, active vendors.

    - anonymous            -> redirected to login
    - non-vendor roles     -> 403 (unchanged behaviour)
    - vendor, but store is pending / rejected / inactive / missing
                           -> redirected to the vendor access-status page
    - approved/active vendor -> view runs; the store is exposed as request.vendor_store

    Views must still filter data by request.user (ownership); this decorator
    only decides whether the user may use vendor features at all.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user.is_vendor_role:
            raise PermissionDenied
        store = get_vendor_store(user)
        if not vendor_has_access(user, store):
            return redirect('vendors:access_status')
        request.vendor_store = store
        return view_func(request, *args, **kwargs)
    return wrapper
