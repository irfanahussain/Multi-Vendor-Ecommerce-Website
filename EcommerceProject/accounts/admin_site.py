from functools import update_wrapper

from django.contrib import messages
from django.contrib.admin import AdminSite
from django.shortcuts import redirect


class RoleAdminSite(AdminSite):
    """Django Admin is for Super Admin accounts only.

    Admin, Vendor and Customer accounts are refused even when is_staff=True
    (set by hand, by a bulk update or by a fixture). Django permissions from
    Groups cannot open the door for them either.
    """

    def has_permission(self, request):
        return bool(getattr(request.user, 'can_use_django_admin', False))

    def admin_view(self, view, cacheable=False):
        # Django's default gate sends a signed-in user who is refused to /admin/login/ first.
        # Send them straight to their own dashboard instead, with the same plain message.
        wrapped = super().admin_view(view, cacheable)

        def gated(request, *args, **kwargs):
            if request.user.is_authenticated and not self.has_permission(request):
                messages.info(request, 'Django Admin is only for Super Admin accounts. '
                                       'You can manage the store from your dashboard.')
                return redirect('dashboard:redirect')
            return wrapped(request, *args, **kwargs)

        return update_wrapper(gated, view)

    def login(self, request, extra_context=None):
        # A signed-in user who is not allowed in would otherwise see Django's
        # "You are authenticated as ..., but are not authorized to access this page."
        # screen. Send them back to their own dashboard with a plain explanation.
        if request.user.is_authenticated and not self.has_permission(request):
            messages.info(request, 'Django Admin is only for Super Admin accounts. '
                                   'You can manage the store from your dashboard.')
            return redirect('dashboard:redirect')
        return super().login(request, extra_context)
