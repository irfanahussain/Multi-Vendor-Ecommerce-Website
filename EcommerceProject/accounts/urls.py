from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/',views.register_view,name='register'),
    path('login/',auth_views.LoginView.as_view(template_name='accounts/login.html'),name='login'),
    path('logout/',auth_views.LogoutView.as_view(),name='logout'),
    path('profile/',views.profile_view,name='profile'),
    path('address/add/',views.address_add,name='address_add'),
    path('address/<int:pk>/delete/',views.address_delete,name='address_delete'),
]
