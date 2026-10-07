from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, default):
    """Return a same-host `next` URL from POST/GET, or `default`."""
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


def customer_required(view_func):
    """Anonymous -> existing login flow (returning to the intended page); non-customers -> 403."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # A POST URL can't be revisited with GET, so fall back to the wishlist page.
            default = request.get_full_path() if request.method == 'GET' else reverse('wishlist:list')
            return redirect_to_login(safe_next(request, default))
        if not request.user.is_customer_role:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper
