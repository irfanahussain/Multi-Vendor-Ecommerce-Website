from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.



class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN='admin','Super Admin'
        VENDOR='vendor','Vendor'
        CUSTOMER='customer','Customer'

    role=models.CharField(max_length=20,choices=Role.choices,default=Role.CUSTOMER)
    mobile_number=models.CharField(max_length=20, blank=True)
    profile_image=models.ImageField(upload_to='profiles/',blank=True,null=True)
    is_active_account=models.BooleanField(default=True)  
    date_joined_display=models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_vendor_role(self):
        return self.role==self.Role.VENDOR

    @property
    def is_customer_role(self):
        return self.role==self.Role.CUSTOMER


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
