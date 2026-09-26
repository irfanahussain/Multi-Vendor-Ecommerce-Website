from django.urls import path
from . import views

app_name = 'vendors'

urlpatterns = [
    path('dashboard/',views.vendor_dashboard,name='dashboard'),
    path('settings/',views.store_settings,name='store_settings'),
    path('store/<int:store_id>/',views.store_public_view,name='store_public'),
]
