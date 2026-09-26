from django.db import models
from django.conf import settings
# Create your models here.



class VendorStore(models.Model):
    class Status(models.TextChoices):
        PENDING='pending','Pending Approval'
        APPROVED='approved','Approved'
        REJECTED='rejected','Rejected'
        ACTIVE='active','Active'
        INACTIVE='inactive','Inactive'

    vendor=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='store')
    store_name=models.CharField(max_length=150)
    logo=models.ImageField(upload_to='vendor_logos/',blank=True,null=True)
    banner=models.ImageField(upload_to='vendor_banners/',blank=True,null=True)
    business_description=models.TextField(blank=True)
    business_address=models.TextField(blank=True)
    contact_number=models.CharField(max_length=20, blank=True)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.PENDING)
    registered_at=models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.store_name

    @property
    def is_active_store(self):
        return self.status in (self.Status.APPROVED, self.Status.ACTIVE)
