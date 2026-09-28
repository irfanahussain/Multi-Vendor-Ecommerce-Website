from django.db import models
from django.conf import settings
from catalog.models import Product

# Create your models here.


class Review(models.Model):
    product=models.ForeignKey(Product,on_delete=models.CASCADE,related_name='reviews')
    customer=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='reviews')
    rating=models.PositiveSmallIntegerField()  
    comment=models.TextField(blank=True)
    is_hidden=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together=('product','customer')  
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.rating}★ by {self.customer.username}"
