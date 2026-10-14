from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """One row per real, completed admin/vendor/customer action. Never created for failed or read-only requests.

    `summary` holds record ids and status names only. Do not store emails, names, phone numbers,
    addresses, payment details or passwords here.
    """

    class Action(models.TextChoices):
        VENDOR_STATUS = 'vendor_status', 'Vendor store status'
        PRODUCT_STATUS = 'product_status', 'Product status'
        ORDER_STATUS = 'order_status', 'Order status'
        STOCK_ADJUST = 'stock_adjust', 'Stock adjustment'
        CUSTOMER_BLOCK = 'customer_block', 'Customer blocked or unblocked'
        COUPON_CREATED = 'coupon_created', 'Coupon created'
        REFUND_STATUS = 'refund_status', 'Refund status'

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name='activity_logs')
    action = models.CharField(max_length=32, choices=Action.choices)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    summary = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_action_display()}: {self.summary}'
