from django.contrib import admin
from .models import Cart, CartItem, Coupon, Order, VendorOrder, OrderItem
# Register your models here.




class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(VendorOrder)
class VendorOrderAdmin(admin.ModelAdmin):
    list_display = ['order', 'vendor', 'status', 'subtotal', 'commission_amount', 'vendor_earning']
    list_filter = ['status']
    inlines = [OrderItemInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer', 'total_amount', 'payment_status', 'created_at']
    search_fields = ['order_number']


admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Coupon)
