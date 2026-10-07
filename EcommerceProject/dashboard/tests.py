import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Brand, Category, Product
from orders.models import Coupon, Order, OrderItem, VendorOrder
from returns_app.models import Refund, ReturnRequest
from vendors.models import VendorStore
from wishlist.models import Wishlist

User = get_user_model()
R = User.Role
PW = 'pw12345!'


def make_user(username, role=R.CUSTOMER, **extra):
    return User.objects.create_user(username, password=PW, role=role, **extra)


def make_vendor(username, status=VendorStore.Status.APPROVED):
    user = make_user(username, R.VENDOR)
    VendorStore.objects.create(vendor=user, store_name=f'{username} store', status=status)
    return user


def make_product(vendor, sku, status=Product.Status.ACTIVE, category=None, brand=None):
    return Product.objects.create(
        vendor=vendor, category=category or Category.objects.get_or_create(name='Misc')[0], brand=brand,
        name=f'Prod {sku}', sku=sku, price=Decimal('100.00'), status=status,
    )


def make_vendor_order(customer, vendor, status='pending', subtotal=Decimal('200.00'), number=None, qty=2, price=Decimal('100.00')):
    number = number or f'ORD-D{Order.objects.count() + 1:04d}'
    order = Order.objects.create(order_number=number, customer=customer, subtotal=subtotal,
                                 total_amount=subtotal)
    vo = VendorOrder.objects.create(order=order, vendor=vendor, status=status, subtotal=subtotal)
    item = OrderItem.objects.create(vendor_order=vo, variant=None, product_name='Gadget', variant_name='Blue',
                                    price=price, quantity=qty)
    return vo, item


class BaseAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_user('cust')
        cls.customer2 = make_user('cust2')
        cls.vendor = make_vendor('vend')
        cls.pending_vendor = make_vendor('pendv', VendorStore.Status.PENDING)
        cls.admin = make_user('adm', R.ADMIN)
        cls.staff_admin = make_user('staffadm', R.ADMIN, is_staff=True)
        cls.super_admin = make_user('sa', R.SUPER_ADMIN)

    def login(self, user):
        self.client.force_login(user)


# =============================================================================
# Access control for every custom Admin Dashboard URL
# =============================================================================

class AdminPageAccessTests(BaseAdminTestCase):
    LIST_PAGES = ['admin_dashboard', 'admin_approvals', 'admin_categories', 'admin_category_add',
                  'admin_brands', 'admin_brand_add', 'admin_coupons', 'admin_coupon_add',
                  'admin_returns', 'admin_refunds', 'admin_commissions']
    PK_PAGES = ['admin_category_edit', 'admin_brand_edit', 'admin_coupon_edit']
    # state-changing URLs: POST only
    ACTION_URLS = ['approve_vendor', 'reject_vendor', 'approve_product', 'reject_product',
                   'admin_category_toggle', 'admin_category_delete', 'admin_brand_toggle', 'admin_brand_delete',
                   'admin_coupon_toggle', 'admin_coupon_delete', 'admin_return_update', 'admin_return_refund',
                   'admin_refund_update']

    def all_urls(self):
        urls = [reverse(f'dashboard:{n}') for n in self.LIST_PAGES]
        urls += [reverse(f'dashboard:{n}', args=[1]) for n in self.PK_PAGES + self.ACTION_URLS]
        return urls

    def test_anonymous_is_sent_to_login(self):
        for url in self.all_urls():
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 302)
                self.assertIn(reverse('accounts:login'), resp['Location'])
                resp = self.client.post(url)
                self.assertEqual(resp.status_code, 302)
                self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_customer_and_vendor_get_403_on_everything(self):
        for user in (self.customer, self.vendor, self.pending_vendor):
            self.login(user)
            for url in self.all_urls():
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url).status_code, 403)

    def test_admin_and_super_admin_can_open_every_list_page(self):
        for user in (self.admin, self.staff_admin, self.super_admin):
            self.login(user)
            for name in self.LIST_PAGES:
                with self.subTest(user=user.username, page=name):
                    self.assertEqual(self.client.get(reverse(f'dashboard:{name}')).status_code, 200)

    def test_action_urls_reject_get_for_admins(self):
        self.login(self.admin)
        for name in self.ACTION_URLS:
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(f'dashboard:{name}', args=[1])).status_code, 405)

    def test_admin_cannot_use_vendor_pages(self):
        for user in (self.admin, self.super_admin):
            self.login(user)
            for url in (reverse('vendors:dashboard'), reverse('vendors:store_settings'),
                        reverse('catalog:vendor_product_list'), reverse('orders:vendor_order_list')):
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_actions_need_a_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        store = self.pending_vendor.store
        resp = strict.post(reverse('dashboard:approve_vendor', args=[store.pk]))
        self.assertEqual(resp.status_code, 403)
        store.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.PENDING)
        cat = Category.objects.create(name='Keep me')
        resp = strict.post(reverse('dashboard:admin_category_delete', args=[cat.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Category.objects.filter(pk=cat.pk).exists())


# =============================================================================
# Sidebar / navigation
# =============================================================================

class AdminNavigationTests(BaseAdminTestCase):
    SIDEBAR = [
        ('admin_dashboard', 'overview'), ('admin_approvals', 'approvals'), ('admin_categories', 'categories'),
        ('admin_brands', 'brands'), ('admin_coupons', 'coupons'), ('admin_returns', 'returns'),
        ('admin_refunds', 'refunds'), ('admin_commissions', 'commissions'),
    ]

    def test_every_page_has_the_full_custom_sidebar_and_marks_itself_active(self):
        self.login(self.admin)
        for name, active in self.SIDEBAR:
            resp = self.client.get(reverse(f'dashboard:{name}'))
            with self.subTest(page=name):
                self.assertEqual(resp.context['active'], active)
                for target, _ in self.SIDEBAR:
                    self.assertContains(resp, f'href="{reverse("dashboard:" + target)}"')

    def test_no_sidebar_link_opens_django_admin_for_a_normal_admin(self):
        self.login(self.admin)
        for name, _ in self.SIDEBAR:
            html = self.client.get(reverse(f'dashboard:{name}')).content.decode()
            with self.subTest(page=name):
                self.assertIsNone(re.search(r'href="/admin/', html))
                self.assertNotIn('Django Admin', html)

    def test_django_admin_link_is_explicit_and_only_for_staff(self):
        for user, expected in ((self.admin, False), (self.staff_admin, True), (self.super_admin, True)):
            self.login(user)
            html = self.client.get(reverse('dashboard:admin_dashboard')).content.decode()
            with self.subTest(user=user.username):
                self.assertEqual('Django Admin (System)' in html, expected)

    def test_sidebar_links_resolve_to_dashboard_urls_not_django_admin(self):
        for name, _ in self.SIDEBAR:
            self.assertTrue(reverse(f'dashboard:{name}').startswith('/dashboard/admin/'), name)


# =============================================================================
# Approvals
# =============================================================================

class ApprovalTests(BaseAdminTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.product = make_product(cls.vendor, 'AP1', status=Product.Status.PENDING)

    def test_approve_and_reject_vendor_via_post(self):
        store = self.pending_vendor.store
        self.login(self.admin)
        resp = self.client.post(reverse('dashboard:approve_vendor', args=[store.pk]))
        self.assertRedirects(resp, reverse('dashboard:admin_approvals'), fetch_redirect_response=False)
        store.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.APPROVED)
        self.client.post(reverse('dashboard:reject_vendor', args=[store.pk]))
        store.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.REJECTED)

    def test_approve_and_reject_product_via_post(self):
        self.login(self.super_admin)
        self.client.post(reverse('dashboard:approve_product', args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.ACTIVE)
        self.client.post(reverse('dashboard:reject_product', args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.REJECTED)

    def test_get_never_changes_any_approval_state(self):
        store = self.pending_vendor.store
        self.login(self.admin)
        for name, obj in (('approve_vendor', store), ('reject_vendor', store),
                          ('approve_product', self.product), ('reject_product', self.product)):
            self.assertEqual(self.client.get(reverse(f'dashboard:{name}', args=[obj.pk])).status_code, 405)
        store.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.PENDING)
        self.assertEqual(self.product.status, Product.Status.PENDING)

    def test_customer_and_vendor_cannot_approve(self):
        store = self.pending_vendor.store
        for user in (self.customer, self.vendor):
            self.login(user)
            self.assertEqual(self.client.post(reverse('dashboard:approve_vendor', args=[store.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse('dashboard:approve_product', args=[self.product.pk])).status_code, 403)
        store.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.PENDING)

    def test_approvals_page_lists_pending_items_with_post_forms(self):
        self.login(self.admin)
        resp = self.client.get(reverse('dashboard:admin_approvals'))
        self.assertContains(resp, 'pendv store')
        self.assertContains(resp, 'Prod AP1')
        self.assertContains(resp, 'method="post"')
        self.assertContains(resp, 'csrfmiddlewaretoken')

    def test_approving_a_vendor_unblocks_the_vendor_dashboard(self):
        self.login(self.pending_vendor)
        self.assertEqual(self.client.get(reverse('vendors:dashboard')).status_code, 302)
        self.login(self.admin)
        self.client.post(reverse('dashboard:approve_vendor', args=[self.pending_vendor.store.pk]))
        self.login(self.pending_vendor)
        self.assertEqual(self.client.get(reverse('vendors:dashboard')).status_code, 200)


# =============================================================================
# Customer dashboard wishlist count
# =============================================================================

class CustomerDashboardWishlistTests(BaseAdminTestCase):
    def test_wishlist_count_is_the_logged_in_customers_real_count(self):
        p1, p2, p3 = (make_product(self.vendor, f'W{i}') for i in range(3))
        Wishlist.objects.create(user=self.customer, product=p1)
        Wishlist.objects.create(user=self.customer, product=p2)
        Wishlist.objects.create(user=self.customer2, product=p3)
        self.login(self.customer)
        resp = self.client.get(reverse('dashboard:customer_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['wishlist_count'], 2)
        self.login(self.customer2)
        self.assertEqual(self.client.get(reverse('dashboard:customer_dashboard')).context['wishlist_count'], 1)

    def test_wishlist_count_updates_and_is_zero_when_empty(self):
        self.login(self.customer)
        self.assertEqual(self.client.get(reverse('dashboard:customer_dashboard')).context['wishlist_count'], 0)
        Wishlist.objects.create(user=self.customer, product=make_product(self.vendor, 'W9'))
        self.assertEqual(self.client.get(reverse('dashboard:customer_dashboard')).context['wishlist_count'], 1)


# =============================================================================
# Categories
# =============================================================================

class CategoryPageTests(BaseAdminTestCase):
    def setUp(self):
        self.login(self.admin)

    def test_create_generates_slug_and_shows_message(self):
        resp = self.client.post(reverse('dashboard:admin_category_add'), {'name': 'Home Decor', 'is_active': 'on'}, follow=True)
        cat = Category.objects.get(name='Home Decor')
        self.assertEqual(cat.slug, 'home-decor')
        self.assertTrue(cat.is_active)
        self.assertContains(resp, 'created')

    def test_duplicate_name_is_a_form_error_not_a_server_error(self):
        Category.objects.create(name='Toys')
        resp = self.client.post(reverse('dashboard:admin_category_add'), {'name': 'Toys'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Category.objects.filter(name='Toys').count(), 1)
        self.assertTrue(resp.context['form'].errors)

    def test_edit_keeps_own_slug_without_clashing_with_itself(self):
        cat = Category.objects.create(name='Shoes')
        resp = self.client.post(reverse('dashboard:admin_category_edit', args=[cat.pk]),
                                {'name': 'Footwear', 'slug': 'shoes', 'is_active': 'on'})
        self.assertEqual(resp.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual((cat.name, cat.slug), ('Footwear', 'shoes'))

    def test_parent_choices_exclude_the_category_and_its_descendants(self):
        root = Category.objects.create(name='Root')
        child = Category.objects.create(name='Child', parent=root)
        grandchild = Category.objects.create(name='Grandchild', parent=child)
        other = Category.objects.create(name='Other')
        resp = self.client.get(reverse('dashboard:admin_category_edit', args=[root.pk]))
        choices = set(resp.context['form'].fields['parent'].queryset.values_list('pk', flat=True))
        self.assertEqual(choices, {other.pk})
        resp = self.client.post(reverse('dashboard:admin_category_edit', args=[root.pk]),
                                {'name': 'Root', 'parent': grandchild.pk, 'is_active': 'on'})
        self.assertEqual(resp.status_code, 200)
        root.refresh_from_db()
        self.assertIsNone(root.parent)

    def test_toggle_flips_active_flag(self):
        cat = Category.objects.create(name='Books')
        self.client.post(reverse('dashboard:admin_category_toggle', args=[cat.pk]))
        cat.refresh_from_db()
        self.assertFalse(cat.is_active)
        self.client.post(reverse('dashboard:admin_category_toggle', args=[cat.pk]))
        cat.refresh_from_db()
        self.assertTrue(cat.is_active)

    def test_delete_is_blocked_when_category_has_products_or_children(self):
        used = Category.objects.create(name='Used')
        make_product(self.vendor, 'U1', category=used)
        parent = Category.objects.create(name='Parent')
        Category.objects.create(name='Kid', parent=parent)
        for cat in (used, parent):
            resp = self.client.post(reverse('dashboard:admin_category_delete', args=[cat.pk]), follow=True)
            self.assertTrue(Category.objects.filter(pk=cat.pk).exists())
            # errors are shown with Bootstrap's "danger" style
            self.assertIn('danger', [m.tags for m in resp.context['messages']])

    def test_delete_empty_category(self):
        cat = Category.objects.create(name='Empty')
        self.client.post(reverse('dashboard:admin_category_delete', args=[cat.pk]))
        self.assertFalse(Category.objects.filter(pk=cat.pk).exists())

    def test_list_search_pagination_and_empty_state(self):
        for i in range(20):
            Category.objects.create(name=f'Cat {i:02d}')
        resp = self.client.get(reverse('dashboard:admin_categories'))
        self.assertEqual(resp.context['page_obj'].paginator.count, 20)
        self.assertEqual(len(resp.context['page_obj']), 15)
        resp = self.client.get(reverse('dashboard:admin_categories'), {'page': 2})
        self.assertEqual(len(resp.context['page_obj']), 5)
        resp = self.client.get(reverse('dashboard:admin_categories'), {'q': 'Cat 07'})
        self.assertEqual(resp.context['page_obj'].paginator.count, 1)
        resp = self.client.get(reverse('dashboard:admin_categories'), {'q': 'zzz-none'})
        self.assertContains(resp, 'No categories match')

    def test_toggle_redirect_ignores_external_next(self):
        cat = Category.objects.create(name='Safe')
        resp = self.client.post(reverse('dashboard:admin_category_toggle', args=[cat.pk]), {'next': 'https://evil.example/'})
        self.assertRedirects(resp, reverse('dashboard:admin_categories'), fetch_redirect_response=False)


# =============================================================================
# Brands
# =============================================================================

class BrandPageTests(BaseAdminTestCase):
    def setUp(self):
        self.login(self.admin)

    def test_create_edit_toggle_delete(self):
        self.client.post(reverse('dashboard:admin_brand_add'), {'name': 'Acme Co', 'is_active': 'on'})
        brand = Brand.objects.get(name='Acme Co')
        self.assertEqual(brand.slug, 'acme-co')
        self.client.post(reverse('dashboard:admin_brand_edit', args=[brand.pk]),
                         {'name': 'Acme Corp', 'slug': 'acme-co', 'is_active': 'on'})
        brand.refresh_from_db()
        self.assertEqual(brand.name, 'Acme Corp')
        self.client.post(reverse('dashboard:admin_brand_toggle', args=[brand.pk]))
        brand.refresh_from_db()
        self.assertFalse(brand.is_active)
        self.client.post(reverse('dashboard:admin_brand_delete', args=[brand.pk]))
        self.assertFalse(Brand.objects.filter(pk=brand.pk).exists())

    def test_duplicate_brand_is_a_form_error(self):
        Brand.objects.create(name='Zed')
        resp = self.client.post(reverse('dashboard:admin_brand_add'), {'name': 'Zed'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Brand.objects.filter(name='Zed').count(), 1)

    def test_brand_used_by_products_cannot_be_deleted(self):
        brand = Brand.objects.create(name='Used Brand')
        make_product(self.vendor, 'B1', brand=brand)
        self.client.post(reverse('dashboard:admin_brand_delete', args=[brand.pk]))
        self.assertTrue(Brand.objects.filter(pk=brand.pk).exists())

    def test_list_and_empty_state(self):
        resp = self.client.get(reverse('dashboard:admin_brands'))
        self.assertContains(resp, 'No brands yet')
        Brand.objects.create(name='Visible Brand')
        self.assertContains(self.client.get(reverse('dashboard:admin_brands')), 'Visible Brand')


# =============================================================================
# Coupons
# =============================================================================

class CouponPageTests(BaseAdminTestCase):
    def setUp(self):
        self.login(self.admin)
        self.url = reverse('dashboard:admin_coupon_add')

    def data(self, **overrides):
        data = {
            'code': 'save10', 'discount_type': 'percent', 'discount_value': '10', 'min_order_amount': '0',
            'max_discount': '', 'start_date': '2030-01-01T00:00', 'expiry_date': '2030-02-01T00:00',
            'usage_limit': '0', 'customer_usage_limit': '1', 'is_active': 'on',
        }
        data.update(overrides)
        return data

    def make_coupon(self, code='OLD', **kwargs):
        now = timezone.now()
        fields = dict(code=code, discount_type='fixed', discount_value=Decimal('5'),
                      start_date=now - timedelta(days=1), expiry_date=now + timedelta(days=5))
        fields.update(kwargs)
        return Coupon.objects.create(**fields)

    def test_create_saves_code_in_capitals_so_checkout_can_find_it(self):
        resp = self.client.post(self.url, self.data())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Coupon.objects.filter(code='SAVE10').exists())

    def test_code_is_unique_ignoring_case(self):
        self.make_coupon('SAVE10')
        resp = self.client.post(self.url, self.data(code='Save10'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Coupon.objects.filter(code__iexact='save10').count(), 1)

    def test_validation_rules(self):
        bad = [
            self.data(discount_value='150'),                                   # percent over 100
            self.data(discount_value='0'),                                     # must be positive
            self.data(expiry_date='2029-12-01T00:00'),                         # expiry before start
            self.data(code='has space'),                                       # bad characters
            self.data(max_discount='-5'),
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                resp = self.client.post(self.url, payload)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(Coupon.objects.count(), 0)

    def test_fixed_amount_over_100_is_allowed(self):
        resp = self.client.post(self.url, self.data(code='FLAT500', discount_type='fixed', discount_value='500'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Coupon.objects.get(code='FLAT500').discount_value, Decimal('500'))

    def test_edit_form_shows_existing_dates_and_saves(self):
        coupon = self.make_coupon('EDITME')
        resp = self.client.get(reverse('dashboard:admin_coupon_edit', args=[coupon.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'datetime-local')
        resp = self.client.post(reverse('dashboard:admin_coupon_edit', args=[coupon.pk]),
                                self.data(code='EDITME', discount_type='fixed', discount_value='7'))
        self.assertEqual(resp.status_code, 302)
        coupon.refresh_from_db()
        self.assertEqual(coupon.discount_value, Decimal('7'))

    def test_toggle(self):
        coupon = self.make_coupon()
        self.client.post(reverse('dashboard:admin_coupon_toggle', args=[coupon.pk]))
        coupon.refresh_from_db()
        self.assertFalse(coupon.is_active)

    def test_delete_blocked_once_used_allowed_otherwise(self):
        used = self.make_coupon('USED', used_count=3)
        unused = self.make_coupon('UNUSED')
        self.client.post(reverse('dashboard:admin_coupon_delete', args=[used.pk]))
        self.client.post(reverse('dashboard:admin_coupon_delete', args=[unused.pk]))
        self.assertTrue(Coupon.objects.filter(pk=used.pk).exists())
        self.assertFalse(Coupon.objects.filter(pk=unused.pk).exists())

    def test_delete_blocked_when_an_order_used_it(self):
        coupon = self.make_coupon('ONORDER')
        Order.objects.create(order_number='ORD-C1', customer=self.customer, subtotal=Decimal('10'),
                             total_amount=Decimal('5'), coupon=coupon)
        self.client.post(reverse('dashboard:admin_coupon_delete', args=[coupon.pk]))
        self.assertTrue(Coupon.objects.filter(pk=coupon.pk).exists())

    def test_state_filter(self):
        now = timezone.now()
        self.make_coupon('LIVE')
        self.make_coupon('GONE', start_date=now - timedelta(days=9), expiry_date=now - timedelta(days=2))
        self.make_coupon('SOON', start_date=now + timedelta(days=2), expiry_date=now + timedelta(days=9))
        self.make_coupon('OFF', is_active=False)
        expected = {'active': {'LIVE'}, 'expired': {'GONE'}, 'scheduled': {'SOON'}, 'inactive': {'OFF'}}
        for state, codes in expected.items():
            resp = self.client.get(reverse('dashboard:admin_coupons'), {'state': state})
            with self.subTest(state=state):
                self.assertEqual({c.code for c in resp.context['page_obj']}, codes)

    def test_empty_state(self):
        self.assertContains(self.client.get(reverse('dashboard:admin_coupons')), 'No coupons yet')


# =============================================================================
# Returns and Refunds
# =============================================================================

class ReturnsRefundsTests(BaseAdminTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vo, cls.item = make_vendor_order(cls.customer, cls.vendor, status='delivered', qty=3, price=Decimal('50.00'))

    def setUp(self):
        self.login(self.admin)

    def make_return(self, status=ReturnRequest.Status.REQUESTED, quantity=2):
        return ReturnRequest.objects.create(order_item=self.item, customer=self.customer, quantity=quantity,
                                            reason='Damaged', status=status)

    def set_status(self, rr, status):
        return self.client.post(reverse('dashboard:admin_return_update', args=[rr.pk]), {'status': status})

    def test_lists_show_rows_and_empty_states(self):
        self.assertContains(self.client.get(reverse('dashboard:admin_returns')), 'No return requests yet')
        self.assertContains(self.client.get(reverse('dashboard:admin_refunds')), 'No refunds yet')
        rr = self.make_return()
        resp = self.client.get(reverse('dashboard:admin_returns'))
        self.assertContains(resp, 'Gadget')
        self.assertContains(resp, 'Damaged')
        self.assertEqual([r.pk for r in resp.context['page_obj']], [rr.pk])

    def test_status_filter(self):
        a = self.make_return()
        b = self.make_return(status=ReturnRequest.Status.APPROVED)
        resp = self.client.get(reverse('dashboard:admin_returns'), {'status': 'approved'})
        self.assertEqual([r.pk for r in resp.context['page_obj']], [b.pk])
        self.assertNotIn(a.pk, [r.pk for r in resp.context['page_obj']])

    def test_allowed_status_path(self):
        rr = self.make_return()
        for status in ('under_review', 'approved', 'returned'):
            self.set_status(rr, status)
            rr.refresh_from_db()
            self.assertEqual(rr.status, status)

    def test_disallowed_changes_are_refused(self):
        rr = self.make_return()
        for status in ('returned', 'refunded', 'nonsense', ''):
            with self.subTest(status=status):
                self.set_status(rr, status)
                rr.refresh_from_db()
                self.assertEqual(rr.status, ReturnRequest.Status.REQUESTED)
        rejected = self.make_return(status=ReturnRequest.Status.REJECTED)
        self.set_status(rejected, 'approved')
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, ReturnRequest.Status.REJECTED)

    def test_refund_only_after_return_and_only_once_with_server_side_amount(self):
        url = lambda rr: reverse('dashboard:admin_return_refund', args=[rr.pk])
        early = self.make_return(status=ReturnRequest.Status.APPROVED)
        self.client.post(url(early), {'amount': '1.00'})
        self.assertFalse(Refund.objects.filter(return_request=early).exists())
        rr = self.make_return(status=ReturnRequest.Status.RETURNED, quantity=2)
        self.client.post(url(rr), {'amount': '9999'})            # a posted amount is ignored
        refund = Refund.objects.get(return_request=rr)
        self.assertEqual(refund.amount, Decimal('100.00'))        # 2 x 50.00
        self.assertEqual(refund.status, Refund.Status.PENDING)
        self.client.post(url(rr))
        self.assertEqual(Refund.objects.filter(return_request=rr).count(), 1)

    def test_completing_a_refund_marks_return_refunded_and_stamps_time(self):
        rr = self.make_return(status=ReturnRequest.Status.RETURNED)
        refund = Refund.objects.create(return_request=rr, amount=Decimal('100'))
        self.client.post(reverse('dashboard:admin_refund_update', args=[refund.pk]), {'status': 'completed'})
        refund.refresh_from_db()
        rr.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.COMPLETED)
        self.assertIsNotNone(refund.processed_at)
        self.assertEqual(rr.status, ReturnRequest.Status.REFUNDED)

    def test_refund_transitions(self):
        rr = self.make_return(status=ReturnRequest.Status.RETURNED)
        refund = Refund.objects.create(return_request=rr, amount=Decimal('10'))
        update = lambda s: self.client.post(reverse('dashboard:admin_refund_update', args=[refund.pk]), {'status': s})
        update('failed')
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'failed')
        update('completed')                       # failed -> completed is not allowed (retry via processing)
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'failed')
        update('processing')
        update('completed')
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'completed')
        update('pending')                         # completed is final
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'completed')

    def test_refund_list_total_and_filter(self):
        rr1 = self.make_return(status=ReturnRequest.Status.RETURNED)
        rr2 = self.make_return(status=ReturnRequest.Status.RETURNED)
        Refund.objects.create(return_request=rr1, amount=Decimal('30'), status='pending')
        Refund.objects.create(return_request=rr2, amount=Decimal('20'), status='completed')
        resp = self.client.get(reverse('dashboard:admin_refunds'))
        self.assertEqual(resp.context['total_amount'], Decimal('50'))
        resp = self.client.get(reverse('dashboard:admin_refunds'), {'status': 'completed'})
        self.assertEqual(resp.context['total_amount'], Decimal('20'))
        self.assertEqual(len(resp.context['page_obj']), 1)

    def test_customers_cannot_touch_returns_or_refunds(self):
        rr = self.make_return()
        self.login(self.customer)
        self.assertEqual(self.set_status(rr, 'approved').status_code, 403)
        rr.refresh_from_db()
        self.assertEqual(rr.status, ReturnRequest.Status.REQUESTED)


# =============================================================================
# Commissions
# =============================================================================

class CommissionPageTests(BaseAdminTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vendor2 = make_vendor('vend2')
        cls.vo1, _ = make_vendor_order(cls.customer, cls.vendor, status='delivered', subtotal=Decimal('1000.00'))
        cls.vo2, _ = make_vendor_order(cls.customer, cls.vendor2, status='pending', subtotal=Decimal('500.00'))
        cls.vo3, _ = make_vendor_order(cls.customer, cls.vendor, status='cancelled', subtotal=Decimal('300.00'))

    def setUp(self):
        self.login(self.admin)

    def test_totals_exclude_cancelled_orders(self):
        resp = self.client.get(reverse('dashboard:admin_commissions'))
        totals = resp.context['totals']
        self.assertEqual(totals['count'], 2)
        self.assertEqual(totals['sales'], Decimal('1500.00'))
        self.assertEqual(totals['commission'], Decimal('150.00'))       # default 10%
        self.assertEqual(totals['earnings'], Decimal('1350.00'))
        self.assertEqual(resp.context['page_obj'].paginator.count, 3)    # the table still lists all three

    def test_vendor_and_status_filters(self):
        resp = self.client.get(reverse('dashboard:admin_commissions'), {'vendor': self.vendor2.pk})
        self.assertEqual([v.pk for v in resp.context['page_obj']], [self.vo2.pk])
        resp = self.client.get(reverse('dashboard:admin_commissions'), {'status': 'cancelled'})
        self.assertEqual([v.pk for v in resp.context['page_obj']], [self.vo3.pk])
        resp = self.client.get(reverse('dashboard:admin_commissions'), {'vendor': 'abc'})   # junk is ignored
        self.assertEqual(resp.status_code, 200)

    def test_page_is_read_only(self):
        self.assertEqual(self.client.post(reverse('dashboard:admin_commissions')).status_code, 405)

    def test_empty_state(self):
        VendorOrder.objects.all().delete()
        self.assertContains(self.client.get(reverse('dashboard:admin_commissions')), 'No vendor orders yet')


# =============================================================================
# Error pages
# =============================================================================

class ErrorPageTests(BaseAdminTestCase):
    def test_403_uses_the_friendly_site_page(self):
        self.login(self.customer)
        resp = self.client.get(reverse('dashboard:admin_dashboard'))
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "don't have access", status_code=403)

    def test_404_uses_the_friendly_site_page(self):
        resp = self.client.get('/this/does/not/exist/')
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "couldn't find", status_code=404)

    def test_categories_still_in_navbar_on_error_pages_and_normal_pages(self):
        Category.objects.create(name='NavCat')
        self.assertContains(self.client.get(reverse('catalog:landing')), 'NavCat')
        self.assertContains(self.client.get('/this/does/not/exist/'), 'NavCat', status_code=404)
