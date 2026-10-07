from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager

# Create your models here.



class UserManager(DjangoUserManager):
    """Same as Django's manager, but `createsuperuser` produces a Super Admin role."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', self.model.Role.SUPER_ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER='customer','Customer'
        VENDOR='vendor','Vendor'
        ADMIN='admin','Admin'
        SUPER_ADMIN='super_admin','Super Admin'

    objects = UserManager()

    role=models.CharField(max_length=20,choices=Role.choices,default=Role.CUSTOMER)
    mobile_number=models.CharField(max_length=20, blank=True)
    profile_image=models.ImageField(upload_to='profiles/',blank=True,null=True)
    is_active_account=models.BooleanField(default=True)  
    date_joined_display=models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.role})"

    # --- role -> Django flag sync -------------------------------------------------
    # `role` is the single source of truth for Django's is_staff / is_superuser:
    #   Super Admin -> is_staff + is_superuser (full Django Admin access)
    #   Admin       -> never a superuser; is_staff is left as set (Django Admin access
    #                  only if is_staff is ticked, and then only what Groups/permissions allow)
    #   Vendor / Customer -> never staff, never superuser (no Django Admin access)
    def _sync_role_flags(self):
        if self.role == self.Role.SUPER_ADMIN:
            self.is_staff = True
            self.is_superuser = True
        elif self.role == self.Role.ADMIN:
            self.is_superuser = False
        else:
            self.is_staff = False
            self.is_superuser = False

    def save(self, *args, **kwargs):
        self._sync_role_flags()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'is_staff', 'is_superuser'}
        super().save(*args, **kwargs)

    # --- role checks (mutually exclusive) -----------------------------------------
    @property
    def is_super_admin_role(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    @property
    def is_admin_role(self):
        """Admin OR Super Admin: may use the project's Admin Dashboard."""
        return self.role == self.Role.ADMIN or self.is_super_admin_role

    @property
    def is_vendor_role(self):
        return self.role == self.Role.VENDOR and not self.is_superuser

    @property
    def is_customer_role(self):
        return self.role == self.Role.CUSTOMER and not self.is_superuser


class Address(models.Model):
    user=models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    full_name=models.CharField(max_length=150)
    phone=models.CharField(max_length=20)
    address_line=models.CharField(max_length=255)
    city=models.CharField(max_length=100)
    state=models.CharField(max_length=100)
    pincode=models.CharField(max_length=20)
    is_default=models.BooleanField(default=False)

    def __str__(self):
        return f"{self.full_name} - {self.city}"

    def save(self,*args,**kwargs):
        # Only one default address per user
        if self.is_default:
            Address.objects.filter(user=self.user,is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args,**kwargs)
