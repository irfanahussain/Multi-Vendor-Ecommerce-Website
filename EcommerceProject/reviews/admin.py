from django.contrib import admin
from .models import Review

# Register your models here.

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display=['product','customer','rating','is_hidden','created_at']
    list_filter=['is_hidden','rating']
    actions=['hide_reviews','unhide_reviews']

    def hide_reviews(self,request,queryset):
        queryset.update(is_hidden=True)
    hide_reviews.short_description="Hide selected reviews"

    def unhide_reviews(self, request, queryset):
        queryset.update(is_hidden=False)
    unhide_reviews.short_description="Unhide selected reviews"
