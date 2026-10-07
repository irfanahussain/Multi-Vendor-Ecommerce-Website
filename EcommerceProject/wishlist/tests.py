from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from catalog.models import Category, Product, ProductVariant
from vendors.models import VendorStore
from .models import Wishlist

User = get_user_model()


def make_product(vendor, n, status=Product.Status.ACTIVE, stock=10):
    product = Product.objects.create(
        vendor=vendor, category=Category.objects.get_or_create(name='Misc')[0],
        name=f'Product {n}', sku=f'SKU-{n}', price=Decimal('100.00'),
        discount_price=Decimal('80.00'), status=status,
    )
    ProductVariant.objects.create(product=product, name='Default', sku=f'SKU-{n}-DEF', stock_quantity=stock)
    return product


class WishlistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user('vend', password='pw12345!', role=User.Role.VENDOR)
        VendorStore.objects.create(vendor=cls.vendor, store_name='Vend Store')
        cls.alice = User.objects.create_user('alice', password='pw12345!')
        cls.bob = User.objects.create_user('bob', password='pw12345!')
        cls.p1 = make_product(cls.vendor, 1)
        cls.p2 = make_product(cls.vendor, 2)

    def login(self, user):
        self.client.force_login(user)

    # --- add ---------------------------------------------------------------
    def test_add_creates_entry_and_redirects_back(self):
        self.login(self.alice)
        resp = self.client.post(reverse('wishlist:add', args=[self.p1.id]), {'next': '/shop/?page=2'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp['Location'].startswith('/shop/?page=2'))
        self.assertTrue(Wishlist.objects.filter(user=self.alice, product=self.p1).exists())

    def test_add_ignores_external_next(self):
        self.login(self.alice)
        resp = self.client.post(reverse('wishlist:add', args=[self.p1.id]), {'next': 'https://evil.example/'})
        self.assertEqual(resp['Location'], self.p1.get_absolute_url())

    def test_add_requires_post(self):
        self.login(self.alice)
        resp = self.client.get(reverse('wishlist:add', args=[self.p1.id]))
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(Wishlist.objects.count(), 0)

    def test_cannot_add_inactive_or_missing_product(self):
        inactive = make_product(self.vendor, 3, status=Product.Status.INACTIVE)
        self.login(self.alice)
        self.assertEqual(self.client.post(reverse('wishlist:add', args=[inactive.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('wishlist:add', args=[99999])).status_code, 404)
        self.assertEqual(Wishlist.objects.count(), 0)

    # --- duplicates --------------------------------------------------------
    def test_duplicate_add_creates_single_entry(self):
        self.login(self.alice)
        url = reverse('wishlist:add', args=[self.p1.id])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(Wishlist.objects.filter(user=self.alice, product=self.p1).count(), 1)

    def test_database_rejects_duplicate_rows(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Wishlist.objects.create(user=self.alice, product=self.p1)

    # --- remove ------------------------------------------------------------
    def test_remove_deletes_entry(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        self.login(self.alice)
        resp = self.client.post(reverse('wishlist:remove', args=[self.p1.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Wishlist.objects.filter(user=self.alice).exists())

    def test_remove_of_item_not_in_wishlist_is_harmless(self):
        self.login(self.alice)
        resp = self.client.post(reverse('wishlist:remove', args=[self.p1.id]))
        self.assertEqual(resp.status_code, 302)

    # --- list --------------------------------------------------------------
    def test_list_shows_product_details(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        self.login(self.alice)
        resp = self.client.get(reverse('wishlist:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Product 1')
        self.assertContains(resp, 'Vend Store')
        self.assertContains(resp, '₹80.00')
        self.assertContains(resp, 'In stock')
        self.assertContains(resp, self.p1.get_absolute_url())
        self.assertContains(resp, reverse('wishlist:remove', args=[self.p1.id]))

    def test_list_empty_state(self):
        self.login(self.alice)
        self.assertContains(self.client.get(reverse('wishlist:list')), 'Your wishlist is empty')

    def test_list_out_of_stock_label(self):
        p = make_product(self.vendor, 4, stock=0)
        Wishlist.objects.create(user=self.alice, product=p)
        self.login(self.alice)
        self.assertContains(self.client.get(reverse('wishlist:list')), 'Out of stock')

    def test_inactive_product_handled_safely(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        Product.objects.filter(pk=self.p1.pk).update(status=Product.Status.INACTIVE)
        self.login(self.alice)
        resp = self.client.get(reverse('wishlist:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No longer available')
        self.assertNotContains(resp, self.p1.get_absolute_url())
        # ...and it can still be removed.
        self.client.post(reverse('wishlist:remove', args=[self.p1.id]))
        self.assertFalse(Wishlist.objects.exists())

    def test_deleted_product_removes_entry(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        self.p1.delete()
        self.login(self.alice)
        self.assertEqual(self.client.get(reverse('wishlist:list')).status_code, 200)
        self.assertFalse(Wishlist.objects.exists())

    def test_list_query_count_does_not_grow_with_items(self):
        self.login(self.alice)
        Wishlist.objects.create(user=self.alice, product=self.p1)
        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse('wishlist:list'))
        for n in range(10, 16):
            Wishlist.objects.create(user=self.alice, product=make_product(self.vendor, n))
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse('wishlist:list'))
        self.assertEqual(len(one), len(many))

    # --- authentication / CSRF --------------------------------------------
    def test_anonymous_is_sent_to_login_and_returns_after(self):
        resp = self.client.get(reverse('wishlist:list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])
        self.assertIn('next=/wishlist/', resp['Location'])

    def test_anonymous_cannot_add_or_remove(self):
        Wishlist.objects.create(user=self.alice, product=self.p2)
        for name, pid in (('wishlist:add', self.p1.id), ('wishlist:remove', self.p2.id)):
            resp = self.client.post(reverse(name, args=[pid]), {'next': self.p1.get_absolute_url()})
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse('accounts:login'), resp['Location'])
        self.assertEqual(Wishlist.objects.count(), 1)

    def test_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        resp = client.post(reverse('wishlist:add', args=[self.p1.id]))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Wishlist.objects.count(), 0)

    def test_vendor_cannot_use_wishlist(self):
        self.login(self.vendor)
        self.assertEqual(self.client.get(reverse('wishlist:list')).status_code, 403)
        self.assertEqual(self.client.post(reverse('wishlist:add', args=[self.p1.id])).status_code, 403)

    # --- isolation ---------------------------------------------------------
    def test_customers_only_see_their_own_wishlist(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        Wishlist.objects.create(user=self.bob, product=self.p2)
        self.login(self.bob)
        resp = self.client.get(reverse('wishlist:list'))
        self.assertContains(resp, 'Product 2')
        self.assertNotContains(resp, 'Product 1')

    def test_customer_cannot_remove_another_customers_entry(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        self.login(self.bob)
        self.client.post(reverse('wishlist:remove', args=[self.p1.id]))
        self.assertTrue(Wishlist.objects.filter(user=self.alice, product=self.p1).exists())

    def test_submitted_user_id_is_ignored(self):
        self.login(self.bob)
        self.client.post(reverse('wishlist:add', args=[self.p1.id]), {'user': self.alice.id, 'user_id': self.alice.id})
        self.assertFalse(Wishlist.objects.filter(user=self.alice).exists())
        self.assertTrue(Wishlist.objects.filter(user=self.bob, product=self.p1).exists())

    # --- UI integration ----------------------------------------------------
    def test_shop_and_detail_show_wishlist_state(self):
        Wishlist.objects.create(user=self.alice, product=self.p1)
        self.login(self.alice)
        shop = self.client.get(reverse('catalog:home'))
        self.assertContains(shop, reverse('wishlist:remove', args=[self.p1.id]))
        self.assertContains(shop, reverse('wishlist:add', args=[self.p2.id]))
        detail = self.client.get(self.p1.get_absolute_url())
        self.assertContains(detail, 'Saved to wishlist')

    def test_anonymous_heart_links_to_login_with_next(self):
        resp = self.client.get(self.p1.get_absolute_url())
        self.assertContains(resp, 'accounts/login/?next=')
        self.assertNotContains(resp, reverse('wishlist:add', args=[self.p1.id]))

    def test_shop_page_wishlist_lookup_is_one_query(self):
        for n in range(20, 30):
            make_product(self.vendor, n)
        self.login(self.alice)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('catalog:home'))
        lookups = [q for q in ctx.captured_queries if 'wishlist_wishlist' in q['sql']]
        self.assertEqual(len(lookups), 1)
