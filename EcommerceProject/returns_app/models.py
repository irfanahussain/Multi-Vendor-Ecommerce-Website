from django.db import models
from django.conf import settings
from orders.models import OrderItem

# Create your models here.


class ReturnRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Return Requested'
        UNDER_REVIEW = 'under_review', 'Under Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        RETURNED = 'returned', 'Product Returned'
        REFUNDED = 'refunded', 'Refund Processed'

    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='return_requests')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='return_requests')
    quantity = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return #{self.pk} - {self.order_item.product_name}"


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    return_request = models.OneToOneField(ReturnRequest, on_delete=models.CASCADE, related_name='refund')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Refund for {self.return_request}"
