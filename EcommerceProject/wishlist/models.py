from django.conf import settings
from django.db import models


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_wishlist_user_product'),
        ]
        indexes = [
            models.Index(fields=['user', '-created_at'], name='wishlist_user_created_idx'),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.product_id}"
