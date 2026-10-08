from django.urls import path
from . import views, admin_views, admin_sections

app_name = 'dashboard'

urlpatterns = [
    path('', views.redirect_by_role, name='redirect'),
    path('customer/', views.customer_dashboard, name='customer_dashboard'),

    # ---- custom Admin Dashboard (Admin + Super Admin roles) ----
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/approvals/', views.admin_approvals, name='admin_approvals'),
    path('admin/vendor/<int:pk>/approve/', views.approve_vendor, name='approve_vendor'),
    path('admin/vendor/<int:pk>/reject/', views.reject_vendor, name='reject_vendor'),
    path('admin/product/<int:pk>/approve/', views.approve_product, name='approve_product'),
    path('admin/product/<int:pk>/reject/', views.reject_product, name='reject_product'),

    path('admin/categories/', admin_views.category_list, name='admin_categories'),
    path('admin/categories/add/', admin_views.category_add, name='admin_category_add'),
    path('admin/categories/<int:pk>/edit/', admin_views.category_edit, name='admin_category_edit'),
    path('admin/categories/<int:pk>/toggle/', admin_views.category_toggle, name='admin_category_toggle'),
    path('admin/categories/<int:pk>/delete/', admin_views.category_delete, name='admin_category_delete'),

    path('admin/brands/', admin_views.brand_list, name='admin_brands'),
    path('admin/brands/add/', admin_views.brand_add, name='admin_brand_add'),
    path('admin/brands/<int:pk>/edit/', admin_views.brand_edit, name='admin_brand_edit'),
    path('admin/brands/<int:pk>/toggle/', admin_views.brand_toggle, name='admin_brand_toggle'),
    path('admin/brands/<int:pk>/delete/', admin_views.brand_delete, name='admin_brand_delete'),

    path('admin/coupons/', admin_views.coupon_list, name='admin_coupons'),
    path('admin/coupons/add/', admin_views.coupon_add, name='admin_coupon_add'),
    path('admin/coupons/<int:pk>/edit/', admin_views.coupon_edit, name='admin_coupon_edit'),
    path('admin/coupons/<int:pk>/toggle/', admin_views.coupon_toggle, name='admin_coupon_toggle'),
    path('admin/coupons/<int:pk>/delete/', admin_views.coupon_delete, name='admin_coupon_delete'),

    path('admin/returns/', admin_views.return_list, name='admin_returns'),
    path('admin/returns/<int:pk>/status/', admin_views.return_update, name='admin_return_update'),
    path('admin/returns/<int:pk>/refund/', admin_views.return_refund_create, name='admin_return_refund'),

    path('admin/refunds/', admin_views.refund_list, name='admin_refunds'),
    path('admin/refunds/<int:pk>/status/', admin_views.refund_update, name='admin_refund_update'),

    path('admin/commissions/', admin_views.commission_list, name='admin_commissions'),

    path('admin/vendors/', admin_sections.vendor_list, name='admin_vendors'),
    path('admin/vendors/<int:pk>/status/', admin_sections.vendor_set_status, name='admin_vendor_status'),
    path('admin/customers/', admin_sections.customer_list, name='admin_customers'),
    path('admin/customers/<int:pk>/toggle/', admin_sections.customer_toggle, name='admin_customer_toggle'),
    path('admin/products/', admin_sections.product_list, name='admin_products'),
    path('admin/products/<int:pk>/status/', admin_sections.product_set_status, name='admin_product_status'),
    path('admin/orders/', admin_sections.order_list, name='admin_orders'),
    path('admin/orders/<int:pk>/', admin_sections.order_detail, name='admin_order_detail'),
    path('admin/promotions/', admin_sections.promotions, name='admin_promotions'),
    path('admin/reports/', admin_sections.reports, name='admin_reports'),
    path('admin/settings/', admin_sections.settings_page, name='admin_settings'),
]
