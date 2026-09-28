from django.contrib import admin
from .models import ReturnRequest, Refund

# Register your models here.

@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'order_item', 'customer', 'status', 'created_at']
    list_filter = ['status']


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ['return_request', 'amount', 'status', 'processed_at']
