from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied

from .models import User, Address


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'groups')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Role', {
            'fields': ('role',),
            'description': (
                'Application role. Super Admin = full Django Admin/superuser access. '
                'Admin = Admin Dashboard, never a superuser (tick "Staff status" and add '
                'Groups only if they should also use Django Admin). '
                'Vendor and Customer never get Django Admin access.'
            ),
        }),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'mobile_number', 'profile_image')}),
        ('Permissions', {
            'fields': ('is_active', 'is_active_account', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': 'Superuser status follows the role and cannot be edited here.',
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'role', 'password1', 'password2'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        # is_superuser is derived from role (see User.save), so never edited directly.
        return tuple(super().get_readonly_fields(request, obj)) + ('is_superuser',)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        # Only a Super Admin may hand out the Super Admin role.
        if db_field.name == 'role' and not request.user.is_superuser:
            kwargs['choices'] = [c for c in db_field.choices if c[0] != User.Role.SUPER_ADMIN]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def _protected(self, request, obj):
        return obj is not None and obj.is_super_admin_role and not request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        if self._protected(request, obj):
            return False
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if self._protected(request, obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._protected(request, obj):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if obj.role == User.Role.SUPER_ADMIN and not request.user.is_superuser:
            raise PermissionDenied
        super().save_model(request, obj, form, change)


admin.site.register(Address)
