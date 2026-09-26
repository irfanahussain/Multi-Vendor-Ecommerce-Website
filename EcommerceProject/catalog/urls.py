from django.urls import path
from . import views

app_name='catalog'

urlpatterns = [
    path('',views.home,name='home'),
    path('product/<slug:slug>/',views.product_detail, name='product_detail'),

    path('vendor/products/',views.vendor_product_list,name='vendor_product_list'),
    path('vendor/products/add/',views.vendor_product_create,name='vendor_product_create'),
    path('vendor/products/<int:pk>/edit/',views.vendor_product_edit,name='vendor_product_edit'),
    path('vendor/products/<int:pk>/variants/',views.vendor_product_variants,name='vendor_product_variants'),
    path('vendor/variants/<int:pk>/stock/',views.vendor_variant_stock,name='vendor_variant_stock'),
]
