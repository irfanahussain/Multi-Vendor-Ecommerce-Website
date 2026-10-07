from django.urls import path
from . import views

app_name = 'wishlist'

urlpatterns = [
    path('', views.wishlist_view, name='list'),
    path('add/<int:product_id>/', views.wishlist_add, name='add'),
    path('remove/<int:product_id>/', views.wishlist_remove, name='remove'),
]
