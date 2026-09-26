from django.contrib import admin
from .models import VendorStore

# Register your models here.




@admin.register(VendorStore)
class VendorStoreAdmin(admin.ModelAdmin):
    list_display = ['store_name', 'vendor', 'status', 'registered_at']
    list_filter = ['status']
    actions = ['approve_stores', 'reject_stores']

    def approve_stores(self, request, queryset):
        queryset.update(status=VendorStore.Status.APPROVED)
    approve_stores.short_description = "Approve selected vendor stores"

    def reject_stores(self, request, queryset):
        queryset.update(status=VendorStore.Status.REJECTED)
    reject_stores.short_description = "Reject selected vendor stores"
