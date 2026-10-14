"""Dashboard totals after returns: overview, vendor dashboard, commissions and reports agree with each other.

Money rule being tested (see orders/finance.py): commission and earnings use the sub-order net of units
received back; sales on sub-order based pages are net; customer-order totals stay gross.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductVariant
from orders.models import Order, OrderItem, VendorOrder
from returns_app.models import ReturnRequest
from returns_app.services import mark_return_received
from vendors.models import VendorStore

User = get_user_model()
PW = 'pw12345!'
RS = ReturnRequest.Status


class DashboardTotalsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('adm', password=PW, role=User.Role.ADMIN)
        self.customer = User.objects.create_user('cust', password=PW, role=User.Role.CUSTOMER)
        self.vendor = User.objects.create_user('vend', password=PW, role=User.Role.VENDOR)
        VendorStore.objects.create(vendor=self.vendor, store_name='Vend', status=VendorStore.Status.APPROVED)
        self.product = Product.objects.create(vendor=self.vendor, category=Category.objects.create(name='Misc'),
                                              name='Gadget', sku='G', price=Decimal('100.00'),
                                              status=Product.Status.ACTIVE)
        self.counter = 0

    def make_order(self, status=VendorOrder.Status.DELIVERED, qty=3, price=Decimal('100.00')):
        """One customer order with one sub-order for the vendor. Sub-order subtotal = qty x price."""
        self.counter += 1
        subtotal = qty * price
        order = Order.objects.create(order_number=f'ORD-DT{self.counter}', customer=self.customer,
                                     subtotal=subtotal, total_amount=subtotal)
        vo = VendorOrder.objects.create(order=order, vendor=self.vendor, status=status, subtotal=subtotal)
        item = OrderItem.objects.create(vendor_order=vo, variant=None, product_name='Gadget', variant_name='',
                                        price=price, quantity=qty)
        return vo, item

    def partial_return_one_unit(self, item):
        rr = ReturnRequest.objects.create(order_item=item, customer=self.customer, quantity=1, reason='x',
                                          status=RS.APPROVED)
        mark_return_received(rr.pk)

    # ---- admin overview ------------------------------------------------------------------------

    def test_overview_chart_range_switches_and_unknown_values_fall_back_to_30_days(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard:admin_dashboard'))
        self.assertEqual(resp.context['range_key'], '30d')
        self.assertEqual(len(resp.context['sales_chart']['bars']), 30)
        resp = self.client.get(reverse('dashboard:admin_dashboard'), {'range': '12m'})
        self.assertEqual(resp.context['range_key'], '12m')
        self.assertEqual(len(resp.context['orders_chart']['bars']), 12)
        resp = self.client.get(reverse('dashboard:admin_dashboard'), {'range': 'banana'})
        self.assertEqual(resp.context['range_key'], '30d')

    def test_overview_commission_is_net_of_received_returns_and_ignores_cancelled(self):
        vo, item = self.make_order()
        self.partial_return_one_unit(item)                           # 300 gross, 100 back -> net 200
        self.make_order(status=VendorOrder.Status.CANCELLED, qty=5)  # earns nothing
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard:admin_dashboard'))
        self.assertEqual(resp.context['total_commission'], Decimal('20.00'))
        self.assertEqual(resp.context['total_sales'], Decimal('800.00'))   # customer-order sales stay gross: 300 + 500

    def test_overview_fully_returned_sub_order_earns_no_commission(self):
        vo, item = self.make_order(qty=1)
        self.partial_return_one_unit(item)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:admin_dashboard')).context['total_commission'],
                         Decimal('0.00'))

    def test_overview_thirty_day_cards_and_chart_count_the_same_orders(self):
        self.make_order()
        old_vo, _ = self.make_order()
        Order.objects.filter(pk=old_vo.order_id).update(created_at=timezone.now() - timedelta(days=40))
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('dashboard:admin_dashboard'))
        self.assertEqual(resp.context['total_orders'], 2)
        self.assertEqual(resp.context['orders_30d'], 1)
        self.assertEqual(resp.context['orders_chart']['total'], 1)

    # ---- vendor dashboard, commissions, reports ------------------------------------------------

    def test_vendor_dashboard_sales_commission_and_earnings_are_net_after_partial_return(self):
        vo, item = self.make_order()
        self.partial_return_one_unit(item)
        self.client.force_login(self.vendor)
        ctx = self.client.get(reverse('vendors:dashboard')).context
        self.assertEqual(ctx['total_sales'], Decimal('200.00'))
        self.assertEqual(ctx['total_commission'], Decimal('20.00'))
        self.assertEqual(ctx['net_earnings'], Decimal('180.00'))

    def test_commission_page_totals_are_net(self):
        vo, item = self.make_order()
        self.partial_return_one_unit(item)
        self.client.force_login(self.admin)
        totals = self.client.get(reverse('dashboard:admin_commissions')).context['totals']
        self.assertEqual(totals['sales'], Decimal('200.00'))
        self.assertEqual(totals['commission'], Decimal('20.00'))
        self.assertEqual(totals['earnings'], Decimal('180.00'))

    def test_reports_sales_and_top_product_units_are_net(self):
        vo, item = self.make_order()
        self.partial_return_one_unit(item)
        self.client.force_login(self.admin)
        ctx = self.client.get(reverse('dashboard:admin_reports'), {'range': 'all'}).context
        self.assertEqual(ctx['sales'], Decimal('200.00'))
        self.assertEqual(ctx['commission'], Decimal('20.00'))
        self.assertEqual(ctx['top_products'][0]['units'], 2)               # 3 bought, 1 back
        self.assertEqual(ctx['top_products'][0]['revenue'], Decimal('200.00'))

    def test_vendor_dashboard_excludes_fully_returned_sub_order(self):
        vo, item = self.make_order(qty=1)
        self.partial_return_one_unit(item)
        self.client.force_login(self.vendor)
        ctx = self.client.get(reverse('vendors:dashboard')).context
        self.assertEqual(ctx['total_sales'], Decimal('0'))
