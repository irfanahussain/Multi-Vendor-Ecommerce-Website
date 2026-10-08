from django.contrib import messages
from django.contrib.admin import AdminSite
from django.shortcuts import redirect


class RoleAdminSite(AdminSite):
    """Django Admin is only for the Admin and Super Admin roles.

    Customers and Vendors are refused even if an is_staff flag was set on them
    by a bulk update or a fixture. On top of the role check, Django's usual
    is_active + is_staff requirement still applies, and what an Admin can do
    inside is still governed by their Groups/permissions (Super Admin: everything).
    """

    def has_permission(self, request):
        user = request.user
        return bool(user.is_active and user.is_staff and getattr(user, 'is_admin_role', False))

    def login(self, request, extra_context=None):
        # A signed-in user who is not allowed in would otherwise see Django's
        # "You are authenticated as ..., but are not authorized to access this page."
        # screen. Send them back to their own dashboard with a plain explanation.
        if request.user.is_authenticated and not self.has_permission(request):
            messages.info(request, 'Django Admin is only for staff accounts. '
                                   'You can manage the store from your dashboard.')
            return redirect('dashboard:redirect')
        return super().login(request, extra_context)
