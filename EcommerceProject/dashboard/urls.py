from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.redirect_by_role, name='redirect'),
    path('customer/', views.customer_dashboard, name='customer_dashboard'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/vendor/<int:pk>/approve/', views.approve_vendor, name='approve_vendor'),
    path('admin/vendor/<int:pk>/reject/', views.reject_vendor, name='reject_vendor'),
    path('admin/product/<int:pk>/approve/', views.approve_product, name='approve_product'),
    path('admin/product/<int:pk>/reject/', views.reject_product, name='reject_product'),
]
