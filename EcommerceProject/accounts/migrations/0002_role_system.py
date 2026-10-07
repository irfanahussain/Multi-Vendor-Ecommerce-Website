import accounts.models
from django.db import migrations, models


def split_admin_roles(apps, schema_editor):
    """Map existing accounts onto the 4-role system.

    - any Django superuser (role 'admin' or the 'customer' default that
      `createsuperuser` used to leave behind)  -> Super Admin
    - remaining role 'admin' (not a superuser)  -> Admin (least privilege)
    - customers / vendors never keep staff status (no Django Admin access)
    Groups and permissions are not touched.
    """
    User = apps.get_model('accounts', 'User')
    User.objects.filter(is_superuser=True).update(role='super_admin', is_staff=True)
    User.objects.filter(role='admin', is_superuser=False).update(role='admin')
    User.objects.filter(role__in=['customer', 'vendor']).update(is_staff=False)


def merge_admin_roles(apps, schema_editor):
    """Reverse: the old schema only knows 'admin' (displayed "Super Admin")."""
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role='super_admin').update(role='admin')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelManagers(
            name='user',
            managers=[
                ('objects', accounts.models.UserManager()),
            ],
        ),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[('customer', 'Customer'), ('vendor', 'Vendor'), ('admin', 'Admin'), ('super_admin', 'Super Admin')],
                default='customer', max_length=20),
        ),
        migrations.RunPython(split_admin_roles, merge_admin_roles),
    ]
