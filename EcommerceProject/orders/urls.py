from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:variant_id>/', views.cart_add, name='cart_add'),
    path('cart/update/<int:item_id>/', views.cart_update, name='cart_update'),
    path('cart/remove/<int:item_id>/', views.cart_remove, name='cart_remove'),
    path('cart/coupon/apply/', views.apply_coupon, name='apply_coupon'),
    path('cart/coupon/remove/', views.remove_coupon, name='remove_coupon'),

    path('checkout/', views.checkout, name='checkout'),
    path('buy-now/', views.buy_now, name='buy_now'),
    path('checkout/buy-now/', views.checkout_buy_now, name='checkout_buy_now'),

    path('my-orders/', views.order_list, name='order_list'),
    path('my-orders/<str:order_number>/', views.order_detail, name='order_detail'),
    path('my-orders/<str:order_number>/track/', views.order_track, name='order_track'),
    path('vendor-order/<int:pk>/cancel/', views.cancel_vendor_order, name='cancel_vendor_order'),

    path('vendor/orders/', views.vendor_order_list, name='vendor_order_list'),
    path('vendor/orders/<int:pk>/', views.vendor_order_detail, name='vendor_order_detail'),
]
