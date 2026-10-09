"""Shop listing, category filtering, product page and role-aware navbar."""
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from vendors.models import VendorStore

from .models import Brand, Category, Product, ProductVariant

User = get_user_model()
R = User.Role
PW = 'pw12345!'
EMPTY_TEXT = 'No products match these filters. Try clearing a filter or widening the price range.'


def make_user(username, role=R.CUSTOMER):
    return User.objects.create_user(username, password=PW, role=role)


def make_vendor(username='shopvend'):
    user = make_user(username, R.VENDOR)
    VendorStore.objects.create(vendor=user, store_name=f'{username} store', status=VendorStore.Status.APPROVED)
    return user


def make_product(vendor, sku, category=None, status=Product.Status.ACTIVE, price='100.00', brand=None, stock=None):
    product = Product.objects.create(vendor=vendor, category=category, brand=brand, name=f'Item {sku}', sku=sku,
                                     price=Decimal(price), status=status)
    if stock is not None:
        ProductVariant.objects.create(product=product, name='Default', sku=f'{sku}-V', stock_quantity=stock)
    return product


def shown(resp):
    return [p.pk for p in resp.context['page_obj']]


class ShopFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor()
        cls.clothing = Category.objects.create(name='Clothing')
        cls.shirts = Category.objects.create(name='Shirts', parent=cls.clothing)
        cls.gadgets = Category.objects.create(name='Gadgets')
        cls.in_parent = make_product(cls.vendor, 'P1', cls.clothing)
        cls.in_child = make_product(cls.vendor, 'C1', cls.shirts)
        cls.elsewhere = make_product(cls.vendor, 'G1', cls.gadgets)
        cls.pending = make_product(cls.vendor, 'C2', cls.shirts, status=Product.Status.PENDING)
        cls.inactive = make_product(cls.vendor, 'C3', cls.shirts, status=Product.Status.INACTIVE)
        cls.rejected = make_product(cls.vendor, 'C4', cls.shirts, status=Product.Status.REJECTED)

    def get(self, **params):
        return self.client.get(reverse('catalog:home'), params)

    def test_parent_category_includes_products_from_its_subcategories(self):
        resp = self.get(category='clothing')
        self.assertCountEqual(shown(resp), [self.in_parent.pk, self.in_child.pk])

    def test_subcategory_shows_only_its_own_products(self):
        self.assertEqual(shown(self.get(category='shirts')), [self.in_child.pk])

    def test_other_category_is_not_mixed_in(self):
        self.assertEqual(shown(self.get(category='gadgets')), [self.elsewhere.pk])

    def test_only_active_products_are_ever_listed(self):
        everything = shown(self.get())
        self.assertCountEqual(everything, [self.in_parent.pk, self.in_child.pk, self.elsewhere.pk])
        for hidden in (self.pending, self.inactive, self.rejected):
            self.assertNotIn(hidden.pk, shown(self.get(category='clothing')))

    def test_categories_and_subcategories_come_from_the_database(self):
        resp = self.get()
        tops = list(resp.context['categories'])
        self.assertEqual([c.name for c in tops], ['Clothing', 'Gadgets'])
        clothing = next(c for c in tops if c.pk == self.clothing.pk)
        self.assertEqual([s.name for s in clothing.subcategories.all()], ['Shirts'])
        self.assertContains(resp, 'value="shirts"')
        self.assertContains(resp, 'value="clothing"')

    def test_inactive_subcategory_is_not_offered_as_a_filter(self):
        Category.objects.create(name='Hidden', parent=self.clothing, is_active=False)
        self.assertNotContains(self.get(), 'value="hidden"')

    def test_unknown_category_gives_clean_empty_state_not_an_error(self):
        resp = self.get(category='does-not-exist')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(shown(resp), [])
        self.assertContains(resp, EMPTY_TEXT)

    def test_empty_state_adds_no_fake_products(self):
        resp = self.get(category='gadgets', min_price='99999')
        self.assertEqual(shown(resp), [])
        self.assertContains(resp, EMPTY_TEXT)
        self.assertNotContains(resp, 'class="card product-card"')

    def test_empty_shop_without_filters_uses_a_different_message(self):
        Product.objects.all().delete()
        resp = self.get()
        self.assertContains(resp, 'There are no products in the shop yet')
        self.assertNotContains(resp, EMPTY_TEXT)

    def test_price_filter(self):
        cheap = make_product(self.vendor, 'CH', self.gadgets, price='20.00')
        self.assertEqual(shown(self.get(category='gadgets', max_price='50')), [cheap.pk])
        self.assertEqual(shown(self.get(category='gadgets', min_price='50')), [self.elsewhere.pk])

    def test_brand_filter(self):
        brand = Brand.objects.create(name='Acme')
        branded = make_product(self.vendor, 'BR', self.gadgets, brand=brand)
        self.assertEqual(shown(self.get(brand=brand.pk)), [branded.pk])

    def test_search_and_sort_still_work(self):
        cheap = make_product(self.vendor, 'SORT-A', self.gadgets, price='10.00')
        self.assertEqual(shown(self.get(q='SORT-A')), [cheap.pk])
        low_first = shown(self.get(category='gadgets', sort='price_low'))
        self.assertEqual(low_first, [cheap.pk, self.elsewhere.pk])
        high_first = shown(self.get(category='gadgets', sort='price_high'))
        self.assertEqual(high_first, [self.elsewhere.pk, cheap.pk])

    def test_garbage_filter_values_do_not_crash(self):
        for params in ({'brand': 'abc'}, {'brand': '²'}, {'brand': '9' * 40}, {'min_price': 'abc'}, {'max_price': '1e999999'}, {'min_price': '99999999999999'}, {'min_price': '-5'}, {'max_price': 'NaN'},
                       {'page': 'zzz'}, {'page': '999'}, {'category': '%%%'}):
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 200)

    def test_pagination_keeps_filters_and_pages_work(self):
        for n in range(13):
            make_product(self.vendor, f'PG{n}', self.gadgets)
        def page_links(resp):
            return re.findall(r'href="(\?[^"]*page=\d+)"', resp.content.decode())

        page1 = self.get(category='gadgets', sort='price_low')
        self.assertEqual(len(shown(page1)), 12)
        links = page_links(page1)
        self.assertEqual(len(links), 1)
        for needle in ('category=gadgets', 'sort=price_low', 'page=2'):
            self.assertIn(needle, links[0])
        page2 = self.get(category='gadgets', sort='price_low', page=2)
        self.assertEqual(len(shown(page2)), 2)
        links = page_links(page2)
        self.assertEqual(len(links), 1)
        for needle in ('category=gadgets', 'sort=price_low', 'page=1'):
            self.assertIn(needle, links[0])
        self.assertEqual(page2.context['result_count'], 14)

    def test_results_header_shows_category_name_and_count(self):
        resp = self.get(category='clothing')
        self.assertEqual(resp.context['selected_category_obj'], self.clothing)
        self.assertContains(resp, '2 products')

    def test_card_has_image_fallback_price_and_view_button(self):
        resp = self.get(category='gadgets')
        self.assertContains(resp, 'product-noimg')   # no fake image is generated
        self.assertContains(resp, '₹100.00')
        self.assertContains(resp, 'View details')


class ProductDetailPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor()
        cls.customer = make_user('buyer')
        cls.cat = Category.objects.create(name='Home')
        cls.product = make_product(cls.vendor, 'D1', cls.cat, stock=3)
        cls.sibling = make_product(cls.vendor, 'D2', cls.cat, stock=3)

    def test_page_renders_for_everyone_who_may_see_it(self):
        resp = self.client.get(self.product.get_absolute_url())
        self.assertContains(resp, 'id="variantPrice"')
        self.assertContains(resp, 'Login to buy')
        self.assertContains(resp, 'aria-label="breadcrumb"')
        self.assertContains(resp, 'Description')
        self.assertContains(resp, 'Customer reviews')

    def test_customer_sees_cart_and_buy_now_controls(self):
        self.client.force_login(self.customer)
        resp = self.client.get(self.product.get_absolute_url())
        for needle in ('id="addToCartForm"', 'id="addToCart"', 'id="buyNow"', 'name="variant"', 'qty-minus', 'qty-plus'):
            self.assertContains(resp, needle)

    def test_vendor_and_admin_do_not_get_buy_controls(self):
        for user in (self.vendor, make_user('adm', R.ADMIN)):
            self.client.force_login(user)
            resp = self.client.get(self.product.get_absolute_url())
            with self.subTest(user=user.username):
                self.assertNotContains(resp, 'id="addToCartForm"')

    def test_rating_is_computed_for_the_stars(self):
        resp = self.client.get(self.product.get_absolute_url())
        self.assertEqual(resp.context['avg_rating'], 0)
        self.assertEqual(len(resp.context['rating_counts']), 5)

    def test_related_products_use_the_same_cards_and_exclude_the_product_itself(self):
        resp = self.client.get(self.product.get_absolute_url())
        self.assertContains(resp, f'id="product-{self.sibling.pk}"')
        self.assertNotContains(resp, f'id="product-{self.product.pk}"')

    def test_product_without_category_or_variants_still_renders(self):
        bare = make_product(self.vendor, 'D3')
        resp = self.client.get(bare.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'not available to order right now')
        self.assertNotContains(resp, 'Related products')

    def test_inactive_product_page_is_hidden_from_customers(self):
        hidden = make_product(self.vendor, 'D4', self.cat, status=Product.Status.INACTIVE, stock=1)
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 404)


class RoleNavbarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = make_user('navcust')
        cls.vendor = make_vendor('navvend')
        cls.admin = make_user('navadmin', R.ADMIN)
        cls.super_admin = make_user('navsuper', R.SUPER_ADMIN)
        parent = Category.objects.create(name='Fashion')
        Category.objects.create(name='Sneakers', parent=parent)

    def html(self, user=None):
        if user:
            self.client.force_login(user)
        return self.client.get(reverse('catalog:home')).content.decode()

    def test_every_role_gets_the_same_core_navbar(self):
        for user in (None, self.customer, self.vendor, self.admin, self.super_admin):
            html = self.html(user)
            with self.subTest(user=getattr(user, 'username', 'anonymous')):
                for label in ('MultiMart', 'Home', 'Categories', 'Best Sellers', 'New Arrivals', 'type="search"'):
                    self.assertIn(label, html)
                self.assertIn('navbar-expand-xl', html)    # collapses before it can overflow
                self.assertIn('navbar-toggler', html)

    def test_category_dropdown_lists_subcategories_from_the_database(self):
        html = self.html()
        self.assertIn('category=fashion', html)
        self.assertIn('category=sneakers', html)

    def test_anonymous_sees_login_and_register_only(self):
        html = self.html()
        self.assertIn(reverse('accounts:login'), html)
        self.assertIn(reverse('accounts:register'), html)
        self.assertNotIn(reverse('accounts:logout'), html)
        self.assertNotIn('mm-avatar', html)

    def test_customer_menu(self):
        html = self.html(self.customer)
        for url in (reverse('orders:cart'), reverse('wishlist:list'), reverse('orders:order_list'), reverse('returns:my_returns')):
            self.assertIn(url, html)
        self.assertNotIn('Vendor Dashboard', html)
        self.assertNotIn('Admin Dashboard', html)
        self.assertNotIn(reverse('dashboard:admin_dashboard'), html)
        self.assertNotIn(reverse('catalog:vendor_product_list'), html)

    def test_vendor_menu(self):
        html = self.html(self.vendor)
        for url in (reverse('vendors:dashboard'), reverse('catalog:vendor_product_list'), reverse('orders:vendor_order_list')):
            self.assertIn(url, html)
        self.assertIn('Vendor Dashboard', html)
        self.assertNotIn('Admin Dashboard', html)
        self.assertNotIn(reverse('dashboard:admin_dashboard'), html)
        self.assertNotIn(reverse('orders:cart'), html)
        self.assertNotIn(reverse('wishlist:list'), html)

    def test_admin_and_super_admin_menu(self):
        for user in (self.admin, self.super_admin):
            html = self.html(user)
            with self.subTest(user=user.username):
                self.assertIn('Admin Dashboard', html)
                self.assertIn(reverse('dashboard:admin_dashboard'), html)
                self.assertIn(reverse('dashboard:admin_approvals'), html)
                self.assertNotIn('Vendor Dashboard', html)
                self.assertNotIn(reverse('catalog:vendor_product_list'), html)
                self.assertNotIn(reverse('orders:cart'), html)

    def test_no_role_gets_a_raw_django_admin_link_in_the_navbar(self):
        for user in (None, self.customer, self.vendor, self.admin, self.super_admin):
            html = self.html(user)
            with self.subTest(user=getattr(user, 'username', 'anonymous')):
                self.assertIsNone(re.search(r'href="/admin/', html))

    def test_navbar_is_present_on_product_and_dashboard_pages_too(self):
        product = make_product(make_vendor('othervend'), 'NAV1', Category.objects.first(), stock=2)
        self.client.force_login(self.admin)
        for url in (product.get_absolute_url(), reverse('dashboard:admin_dashboard')):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'navbar-expand-xl')


class EmptyStateRegressionTests(TestCase):
    """Regression tests for the empty product-list branch of catalog/home.html."""

    @classmethod
    def setUpTestData(cls):
        cls.vendor = make_vendor('emptyvend')
        cls.apparel = Category.objects.create(name='Apparel')
        cls.tees = Category.objects.create(name='Tees', parent=cls.apparel)
        cls.vacant = Category.objects.create(name='Vacant')
        cls.tee = make_product(cls.vendor, 'ER1', cls.tees, price='250.00')

    def get(self, **params):
        return self.client.get(reverse('catalog:home'), params)

    def clear_link(self):
        return f'href="{reverse("catalog:home")}">Clear filters</a>'

    def test_empty_shop_shows_shop_message_without_clear_filters(self):
        Product.objects.all().delete()
        resp = self.get()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(shown(resp), [])
        self.assertContains(resp, 'No products found')
        self.assertContains(resp, 'There are no products in the shop yet')
        self.assertNotContains(resp, EMPTY_TEXT)
        self.assertNotContains(resp, self.clear_link())

    def test_category_with_no_products_shows_filtered_empty_state(self):
        resp = self.get(category='vacant')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(shown(resp), [])
        self.assertContains(resp, 'No products found')
        self.assertContains(resp, EMPTY_TEXT)
        self.assertContains(resp, self.clear_link())

    def test_filters_returning_zero_results_show_compact_message_and_clear_link(self):
        for params in ({'min_price': '100000'}, {'min_price': '500', 'max_price': '100'}, {'q': 'no-such-product'}):
            with self.subTest(params=params):
                resp = self.get(**params)
                self.assertEqual(shown(resp), [])
                self.assertContains(resp, 'No products found')
                self.assertContains(resp, EMPTY_TEXT)
                self.assertContains(resp, 'mm-empty-compact')
                self.assertContains(resp, self.clear_link())

    def test_invalid_price_inputs_are_ignored_instead_of_emptying_the_list(self):
        for params in ({'min_price': 'abc'}, {'max_price': 'abc'}, {'min_price': '-5'},
                       {'max_price': 'NaN'}, {'min_price': 'Infinity'}):
            with self.subTest(params=params):
                resp = self.get(**params)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(shown(resp), [self.tee.pk])
                self.assertFalse(resp.context['has_filters'])
                self.assertNotContains(resp, 'No products found')

    def test_valid_price_bounds_still_filter(self):
        resp = self.get(min_price='0', max_price='250')
        self.assertEqual(shown(resp), [self.tee.pk])
        self.assertNotContains(resp, 'No products found')

    def test_parent_category_lists_subcategory_products(self):
        resp = self.get(category='apparel')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(shown(resp), [self.tee.pk])
        self.assertContains(resp, f'id="product-{self.tee.pk}"')
        self.assertContains(resp, '1 product')
        self.assertNotContains(resp, 'No products found')