"""Activity Log: entries for real actions only, Super Admin-only page, filters, no personal data in summaries."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductVariant
from dashboard.models import ActivityLog
from orders.models import Order, OrderItem, VendorOrder
from returns_app.models import Refund, ReturnRequest
from vendors.models import VendorStore

User = get_user_model()
R = User.Role
A = ActivityLog.Action
PW = 'pw12345!'


def make_user(username, role, **extra):
    return User.objects.create_user(username, password=PW, role=role, **extra)


class ActivityBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.super_admin = make_user('boss', R.SUPER_ADMIN)
        cls.admin = make_user('ops_admin', R.ADMIN)
        cls.customer = make_user('shopper_jane', R.CUSTOMER)
        cls.vendor = make_user('seller_acme', R.VENDOR)
        cls.store = VendorStore.objects.create(vendor=cls.vendor, store_name='Acme', status=VendorStore.Status.APPROVED)
        cls.pending_vendor = make_user('pending_seller', R.VENDOR)
        cls.pending_store = VendorStore.objects.create(vendor=cls.pending_vendor, store_name='Pending Co',
                                                       status=VendorStore.Status.PENDING)
        cls.category = Category.objects.create(name='Gadgets')
        cls.pending_product = Product.objects.create(vendor=cls.pending_vendor, category=cls.category,
                                                     name='Widget', sku='W1', price=Decimal('10.00'),
                                                     status=Product.Status.PENDING)
        cls.product = Product.objects.create(vendor=cls.vendor, category=cls.category, name='Gizmo', sku='G1',
                                             price=Decimal('20.00'), status=Product.Status.ACTIVE)
        cls.variant = ProductVariant.objects.create(product=cls.product, name='Default', sku='G1-D', stock_quantity=5)

    def login(self, user):
        self.client.force_login(user)

    def entries(self, action=None):
        qs = ActivityLog.objects.all()
        return qs.filter(action=action) if action else qs

    def make_pending_sub_order(self, customer=None):
        order = Order.objects.create(order_number=f'ORD-{Order.objects.count() + 1}',
                                     customer=customer or self.customer,
                                     subtotal=Decimal('20.00'), total_amount=Decimal('20.00'))
        vo = VendorOrder.objects.create(order=order, vendor=self.vendor, status=VendorOrder.Status.PENDING,
                                        subtotal=Decimal('20.00'))
        item = OrderItem.objects.create(vendor_order=vo, variant=self.variant, product_name='Gizmo',
                                        variant_name='Default', price=Decimal('20.00'), quantity=1)
        return vo, item


class WritesEntriesForRealActions(ActivityBase):
    def test_vendor_approval_and_rejection_are_logged(self):
        self.login(self.admin)
        self.client.post(reverse('dashboard:approve_vendor', args=[self.pending_store.pk]))
        entry = self.entries(A.VENDOR_STATUS).get()
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual((entry.target_type, entry.target_id), ('vendor_store', self.pending_store.pk))
        self.assertEqual(entry.summary, f'Store #{self.pending_store.pk} is now Approved')
        self.client.post(reverse('dashboard:reject_vendor', args=[self.pending_store.pk]))
        self.assertEqual(self.entries(A.VENDOR_STATUS).count(), 2)

    def test_product_approval_and_rejection_are_logged(self):
        self.login(self.admin)
        self.client.post(reverse('dashboard:approve_product', args=[self.pending_product.pk]))
        self.client.post(reverse('dashboard:reject_product', args=[self.pending_product.pk]))
        entries = self.entries(A.PRODUCT_STATUS)
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries.order_by('pk').first().summary,
                         f'Product #{self.pending_product.pk} is now Active')

    def test_customer_block_is_logged_without_username_or_email(self):
        self.login(self.admin)
        self.client.post(reverse('dashboard:admin_customer_toggle', args=[self.customer.pk]))
        entry = self.entries(A.CUSTOMER_BLOCK).get()
        self.assertEqual(entry.summary, f'Customer #{self.customer.pk} is now blocked')
        self.assertNotIn('shopper_jane', entry.summary)
        self.assertNotIn('@', entry.summary)

    def test_vendor_order_status_change_is_logged(self):
        vo, _ = self.make_pending_sub_order()
        self.login(self.vendor)
        self.client.post(reverse('orders:vendor_order_detail', args=[vo.pk]), {'status': 'confirmed'})
        entry = self.entries(A.ORDER_STATUS).get()
        self.assertEqual((entry.target_type, entry.target_id), ('vendor_order', vo.pk))
        self.assertEqual(entry.actor, self.vendor)
        self.assertEqual(entry.summary, f'Sub-order #{vo.pk} is now Confirmed')

    def test_customer_cancellation_is_logged(self):
        vo, _ = self.make_pending_sub_order()
        self.login(self.customer)
        self.client.post(reverse('orders:cancel_vendor_order', args=[vo.pk]))
        entry = self.entries(A.ORDER_STATUS).get()
        self.assertEqual(entry.actor, self.customer)
        self.assertIn('Cancelled', entry.summary)

    def test_stock_adjustment_is_logged_with_signed_change(self):
        self.login(self.vendor)
        self.client.post(reverse('catalog:vendor_variant_stock', args=[self.variant.pk]),
                         {'change_quantity': 3, 'note': 'delivery'})
        entry = self.entries(A.STOCK_ADJUST).get()
        self.assertEqual(entry.summary, f'Variant #{self.variant.pk} stock changed by +3')
        self.assertNotIn('delivery', entry.summary)   # the free-text note is not copied into the log

    def test_refund_status_change_is_logged(self):
        vo, item = self.make_pending_sub_order()
        rr = ReturnRequest.objects.create(order_item=item, customer=self.customer, quantity=1,
                                          reason='Damaged', status=ReturnRequest.Status.RETURNED)
        refund = Refund.objects.create(return_request=rr, amount=Decimal('20.00'))
        self.login(self.admin)
        self.client.post(reverse('dashboard:admin_refund_update', args=[refund.pk]), {'status': 'completed'})
        entry = self.entries(A.REFUND_STATUS).get()
        self.assertEqual((entry.target_type, entry.target_id), ('refund', refund.pk))
        self.assertEqual(entry.summary, f'Refund #{refund.pk} is now Completed')


class WritesNothingForRejectedOrReadOnlyRequests(ActivityBase):
    def test_get_requests_that_would_change_state_write_nothing(self):
        self.login(self.admin)
        self.client.get(reverse('dashboard:approve_vendor', args=[self.pending_store.pk]))
        self.assertFalse(self.entries().exists())

    def test_refused_actions_write_nothing(self):
        self.login(self.customer)
        self.client.post(reverse('dashboard:approve_vendor', args=[self.pending_store.pk]))
        self.client.post(reverse('dashboard:admin_customer_toggle', args=[self.customer.pk]))
        self.assertFalse(self.entries().exists())

    def test_invalid_status_change_writes_nothing(self):
        vo, _ = self.make_pending_sub_order()
        self.login(self.vendor)
        self.client.post(reverse('orders:vendor_order_detail', args=[vo.pk]), {'status': 'delivered'})
        self.assertFalse(self.entries(A.ORDER_STATUS).exists())

    def test_read_only_pages_write_nothing(self):
        self.login(self.super_admin)
        self.client.get(reverse('dashboard:admin_dashboard'))
        self.client.get(reverse('dashboard:admin_activity'))
        self.assertFalse(self.entries().exists())


class ActivityPageAccessTests(ActivityBase):
    def test_super_admin_can_open_the_page(self):
        self.login(self.super_admin)
        self.assertEqual(self.client.get(reverse('dashboard:admin_activity')).status_code, 200)

    def test_normal_admin_gets_403(self):
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:admin_activity')).status_code, 403)

    def test_vendor_and_customer_get_403(self):
        for user in (self.vendor, self.customer):
            self.login(user)
            self.assertEqual(self.client.get(reverse('dashboard:admin_activity')).status_code, 403)

    def test_anonymous_is_sent_to_login(self):
        resp = self.client.get(reverse('dashboard:admin_activity'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_sidebar_link_only_for_super_admin(self):
        url = reverse('dashboard:admin_activity')
        self.login(self.super_admin)
        self.assertContains(self.client.get(reverse('dashboard:admin_dashboard')), f'href="{url}"')
        self.login(self.admin)
        self.assertNotContains(self.client.get(reverse('dashboard:admin_dashboard')), f'href="{url}"')


class ActivityPageContentTests(ActivityBase):
    def setUp(self):
        self.login(self.super_admin)

    def make_entry(self, action, days_ago=0, summary='x'):
        entry = ActivityLog.objects.create(actor=self.admin, action=action, summary=summary,
                                           target_type='', target_id=None)
        if days_ago:
            ActivityLog.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return entry

    def test_filters_by_action_and_period(self):
        self.make_entry(A.VENDOR_STATUS, days_ago=1)
        self.make_entry(A.VENDOR_STATUS, days_ago=60)
        self.make_entry(A.REFUND_STATUS, days_ago=1)
        url = reverse('dashboard:admin_activity')
        ctx = self.client.get(url, {'action': 'vendor_status', 'days': '30'}).context
        self.assertEqual(ctx['page_obj'].paginator.count, 1)
        ctx = self.client.get(url, {'action': 'vendor_status', 'days': 'all'}).context
        self.assertEqual(ctx['page_obj'].paginator.count, 2)
        ctx = self.client.get(url, {'days': '7'}).context
        self.assertEqual(ctx['page_obj'].paginator.count, 2)

    def test_unknown_filter_values_fall_back_to_defaults(self):
        self.make_entry(A.STOCK_ADJUST)
        ctx = self.client.get(reverse('dashboard:admin_activity'), {'action': 'bogus', 'days': 'bogus'}).context
        self.assertEqual(ctx['current_action'], '')
        self.assertEqual(ctx['current_days'], '30')
        self.assertEqual(ctx['page_obj'].paginator.count, 1)

    def test_empty_state_is_shown(self):
        resp = self.client.get(reverse('dashboard:admin_activity'))
        self.assertContains(resp, 'No activity recorded for this filter yet.')

    def test_newest_first(self):
        old = self.make_entry(A.VENDOR_STATUS, days_ago=2, summary='old')
        new = self.make_entry(A.VENDOR_STATUS, days_ago=0, summary='new')
        resp = self.client.get(reverse('dashboard:admin_activity'))
        self.assertEqual([e.pk for e in resp.context['page_obj'].object_list], [new.pk, old.pk])

    def test_deleted_actor_keeps_the_entry(self):
        entry = self.make_entry(A.VENDOR_STATUS)
        self.admin.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.actor)
        self.assertEqual(ActivityLog.objects.count(), 1)


class SummariesNeverHoldPersonalData(ActivityBase):
    def test_no_summary_contains_email_name_or_username(self):
        self.login(self.admin)
        self.client.post(reverse('dashboard:approve_vendor', args=[self.pending_store.pk]))
        self.client.post(reverse('dashboard:admin_customer_toggle', args=[self.customer.pk]))
        for entry in self.entries():
            with self.subTest(summary=entry.summary):
                self.assertNotIn('@', entry.summary)
                for word in ('shopper_jane', 'seller_acme', 'Pending Co', 'Acme', 'Gizmo', 'Widget'):
                    self.assertNotIn(word, entry.summary)
