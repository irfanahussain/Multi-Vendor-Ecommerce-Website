from django.contrib import admin
from .models import Category, Brand,Product,ProductVariant,StockHistory


class ProductVariantInline(admin.TabularInline):
    model=ProductVariant
    extra=1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display=['name','vendor','category','price','status','created_at']
    list_filter=['status','category']
    search_fields=['name','sku']
    inlines=[ProductVariantInline]
    actions=['approve_products', 'reject_products']

    def approve_products(self,request,queryset):
        queryset.update(status=Product.Status.ACTIVE)
    approve_products.short_description="Approve&activate selected products"

    def reject_products(self,request,queryset):
        queryset.update(status=Product.Status.REJECTED)
    reject_products.short_description="Reject selected products"


admin.site.register(Category)
admin.site.register(Brand)
admin.site.register(StockHistory)
