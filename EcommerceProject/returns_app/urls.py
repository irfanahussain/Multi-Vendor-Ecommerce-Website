from django.urls import path
from . import views

app_name = 'returns'

urlpatterns = [
    path('request/<int:order_item_id>/', views.request_return, name='request_return'),
    path('my-returns/', views.my_returns, name='my_returns'),
]
