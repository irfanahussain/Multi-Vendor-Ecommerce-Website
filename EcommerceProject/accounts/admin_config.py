from django.contrib.admin.apps import AdminConfig


class RoleAdminConfig(AdminConfig):
    """Replaces 'django.contrib.admin' so the Django Admin uses RoleAdminSite."""
    default_site = 'accounts.admin_site.RoleAdminSite'
