from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Address
from catalog.models import Category, Product, ProductVariant, StockHistory
from orders.models import Cart, CartItem, Order, OrderItem, VendorOrder
from orders.tracking import build_timeline
from reviews.models import Review
from vendors.models import VendorStore
from wishlist.models import Wishlist

User = get_user_model()


def make_product(vendor, name, sku, status=Product.Status.ACTIVE):
    return Product.objects.create(
        vendor=vendor, category=Category.objects.get_or_create(name='Misc')[0],
        name=name, sku=sku, price=Decimal('100.00'), discount_price=Decimal('80.00'), status=status,
    )


def make_variant(product, name, stock, sku, price=None, is_active=True):
    return ProductVariant.objects.create(
        product=product, name=name, sku=sku, stock_quantity=stock, price=price, is_active=is_active,
    )


class BuyNowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor = User.objects.create_user('vend', password='pw12345!', role=User.Role.VENDOR)
        VendorStore.objects.create(vendor=cls.vendor, store_name='Vend Store')
        cls.alice = User.objects.create_user('alice', password='pw12345!')
        cls.phone = make_product(cls.vendor, 'Phone X', 'PX')
        cls.blue = make_variant(cls.phone, 'Blue', 5, 'PX-BLUE')
        cls.red = make_variant(cls.phone, 'Red', 0, 'PX-RED')
        cls.pricey = make_variant(cls.phone, 'Gold', 9, 'PX-GOLD', price=Decimal('150.00'))
        cls.other = make_product(cls.vendor, 'Case Y', 'CY')
        cls.other_variant = make_variant(cls.other, 'Default', 5, 'CY-DEF')
        cls.url = reverse('orders:buy_now')

    def buy(self, variant=None, quantity=1, product=None, **extra):
        data = {
            'product': (product or self.phone).id,
            'variant': variant.id if variant is not None else '',
            'quantity': quantity,
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def login(self):
        self.client.force_login(self.alice)

    def add_address(self):
        return Address.objects.create(user=self.alice, full_name='Alice A', phone='999', address_line='1 Main St',
                                      city='Pune', state='MH', pincode='411001')

    # --- authentication / method / CSRF -----------------------------------
    def test_requires_authentication(self):
        resp = self.buy(self.blue)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])
        self.assertNotIn('buy_now', self.client.session)

    def test_login_redirect_ignores_external_next(self):
        resp = self.buy(self.blue, next='https://evil.example/')
        self.assertNotIn('evil.example', resp['Location'])
        resp = self.buy(self.blue, next=self.phone.get_absolute_url())
        self.assertIn('next=/product/', resp['Location'])

    def test_checkout_page_requires_authentication(self):
        resp = self.client.get(reverse('orders:checkout_buy_now'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_get_not_allowed_and_csrf_enforced(self):
        self.login()
        self.assertEqual(self.client.get(self.url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(self.url, {'product': self.phone.id, 'variant': self.blue.id, 'quantity': 1}).status_code, 403)

    def test_vendor_cannot_buy_now(self):
        self.client.force_login(self.vendor)
        self.assertEqual(self.buy(self.blue).status_code, 403)

    # --- happy path ---------------------------------------------------------
    def test_valid_buy_now_goes_to_checkout_without_touching_cart(self):
        self.login()
        resp = self.buy(self.blue, 2)
        self.assertRedirects(resp, reverse('orders:checkout_buy_now'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['buy_now'], {'variant_id': self.blue.id, 'quantity': 2})
        self.assertFalse(CartItem.objects.exists())

    def test_checkout_shows_correct_item_and_totals(self):
        self.login()
        self.add_address()
        self.buy(self.blue, 2)
        resp = self.client.get(reverse('orders:checkout_buy_now'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Phone X')
        self.assertContains(resp, 'Blue')
        self.assertContains(resp, '₹160.00')   # 80.00 x 2
        self.assertContains(resp, '₹218.00')   # + 5% tax 8.00 + shipping 50.00

    def test_variant_price_override_is_used(self):
        self.login()
        self.buy(self.pricey, 1)
        resp = self.client.get(reverse('orders:checkout_buy_now'))
        self.assertContains(resp, '₹150.00')

    def test_place_buy_now_order_leaves_cart_alone(self):
        self.login()
        address = self.add_address()
        cart = Cart.objects.create(user=self.alice)
        CartItem.objects.create(cart=cart, variant=self.other_variant, quantity=1)
        self.buy(self.blue, 2)
        resp = self.client.post(reverse('orders:checkout_buy_now'), {'address_id': address.id, 'payment_method': 'cod'})
        order = Order.objects.get(customer=self.alice)
        self.assertRedirects(resp, reverse('orders:order_detail', args=[order.order_number]), fetch_redirect_response=False)
        self.assertEqual(order.total_amount, Decimal('218.00'))
        item = OrderItem.objects.get()
        self.assertEqual((item.variant_id, item.quantity, item.price), (self.blue.id, 2, Decimal('80.00')))
        self.blue.refresh_from_db()
        self.assertEqual(self.blue.stock_quantity, 3)
        # normal cart is untouched, buy-now state is cleared
        self.assertEqual(list(cart.items.values_list('variant_id', 'quantity')), [(self.other_variant.id, 1)])
        self.assertNotIn('buy_now', self.client.session)

    # --- variant validation -------------------------------------------------
    def test_variant_from_another_product_rejected(self):
        self.login()
        resp = self.buy(self.other_variant)
        self.assertRedirects(resp, self.phone.get_absolute_url(), fetch_redirect_response=False)
        self.assertNotIn('buy_now', self.client.session)

    def test_missing_or_garbage_variant_rejected(self):
        self.login()
        for bad in (None, 99999):
            resp = self.buy(SimpleVariant(bad))
            self.assertRedirects(resp, self.phone.get_absolute_url(), fetch_redirect_response=False)
        resp = self.client.post(self.url, {'product': self.phone.id, 'variant': 'abc', 'quantity': 1})
        self.assertRedirects(resp, self.phone.get_absolute_url(), fetch_redirect_response=False)
        self.assertNotIn('buy_now', self.client.session)

    def test_inactive_variant_rejected(self):
        hidden = make_variant(self.phone, 'Hidden', 5, 'PX-HID', is_active=False)
        self.login()
        self.buy(hidden)
        self.assertNotIn('buy_now', self.client.session)

    def test_inactive_or_unknown_product_rejected(self):
        draft = make_product(self.vendor, 'Draft', 'DR', status=Product.Status.INACTIVE)
        v = make_variant(draft, 'Default', 5, 'DR-DEF')
        self.login()
        self.assertRedirects(self.buy(v, product=draft), reverse('catalog:home'), fetch_redirect_response=False)
        resp = self.client.post(self.url, {'product': 99999, 'variant': v.id, 'quantity': 1})
        self.assertRedirects(resp, reverse('catalog:home'), fetch_redirect_response=False)
        self.assertNotIn('buy_now', self.client.session)

    # --- quantity / stock ---------------------------------------------------
    def test_invalid_quantities_rejected(self):
        self.login()
        for q in (0, -3, 'abc', ''):
            resp = self.buy(self.blue, q)
            self.assertRedirects(resp, self.phone.get_absolute_url(), fetch_redirect_response=False)
            self.assertNotIn('buy_now', self.client.session)

    def test_insufficient_stock_rejected(self):
        self.login()
        resp = self.buy(self.blue, 6)
        self.assertRedirects(resp, self.phone.get_absolute_url(), fetch_redirect_response=False)
        self.assertNotIn('buy_now', self.client.session)
        follow = self.client.get(self.phone.get_absolute_url())
        self.assertContains(follow, 'Only 5 left in stock')

    def test_out_of_stock_variant_gives_friendly_message(self):
        self.login()
        self.buy(self.red, 1)
        self.assertNotIn('buy_now', self.client.session)
        self.assertContains(self.client.get(self.phone.get_absolute_url()), 'is out of stock')

    def test_exact_stock_allowed(self):
        self.login()
        self.assertRedirects(self.buy(self.blue, 5), reverse('orders:checkout_buy_now'), fetch_redirect_response=False)

    def test_stock_change_after_buy_now_is_caught_at_checkout(self):
        self.login()
        self.buy(self.blue, 4)
        ProductVariant.objects.filter(pk=self.blue.pk).update(stock_quantity=1)
        resp = self.client.get(reverse('orders:checkout_buy_now'))
        self.assertRedirects(resp, self.phone.get_absolute_url(), fetch_redirect_response=False)
        self.assertNotIn('buy_now', self.client.session)

    def test_checkout_without_buy_now_state_redirects(self):
        self.login()
        resp = self.client.get(reverse('orders:checkout_buy_now'))
        self.assertRedirects(resp, reverse('catalog:home'), fetch_redirect_response=False)

    # --- tampering ----------------------------------------------------------
    def test_browser_supplied_price_is_ignored(self):
        self.login()
        address = self.add_address()
        self.buy(self.blue, 1, price='1.00', total='1.00', unit_price='0.01', total_amount='1')
        self.assertEqual(set(self.client.session['buy_now']), {'variant_id', 'quantity'})
        self.client.post(reverse('orders:checkout_buy_now'),
                         {'address_id': address.id, 'payment_method': 'cod', 'price': '1.00', 'total_amount': '1'})
        order = Order.objects.get()
        self.assertEqual(OrderItem.objects.get().price, Decimal('80.00'))
        self.assertEqual(order.subtotal, Decimal('80.00'))

    def test_price_change_between_steps_uses_current_server_price(self):
        self.login()
        self.buy(self.blue, 1)
        Product.objects.filter(pk=self.phone.pk).update(discount_price=Decimal('70.00'))
        self.assertContains(self.client.get(reverse('orders:checkout_buy_now')), '₹70.00')

    def test_cannot_check_out_another_users_address(self):
        bob = User.objects.create_user('bob', password='pw12345!')
        theirs = Address.objects.create(user=bob, full_name='Bob', phone='1', address_line='x', city='c', state='s', pincode='1')
        self.login()
        self.buy(self.blue, 1)
        resp = self.client.post(reverse('orders:checkout_buy_now'), {'address_id': theirs.id, 'payment_method': 'cod'})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Order.objects.exists())

    # --- existing behaviour still works ------------------------------------
    def test_add_to_cart_still_works(self):
        self.login()
        resp = self.client.post(reverse('orders:cart_add', args=[self.blue.id]), {'quantity': 2})
        self.assertRedirects(resp, reverse('orders:cart'), fetch_redirect_response=False)
        item = CartItem.objects.get()
        self.assertEqual((item.variant_id, item.quantity), (self.blue.id, 2))

    def test_normal_checkout_still_works_after_buy_now_started(self):
        self.login()
        address = self.add_address()
        self.client.post(reverse('orders:cart_add', args=[self.other_variant.id]), {'quantity': 1})
        self.buy(self.blue, 1)  # abandoned Buy Now must not leak into the cart checkout
        page = self.client.get(reverse('orders:checkout'))
        self.assertContains(page, 'Case Y')
        self.assertNotContains(page, 'Phone X')
        self.client.post(reverse('orders:checkout'), {'address_id': address.id, 'payment_method': 'cod'})
        self.assertEqual(OrderItem.objects.get().variant_id, self.other_variant.id)
        self.assertFalse(CartItem.objects.exists())

    def test_empty_cart_checkout_still_redirects(self):
        self.login()
        self.assertRedirects(self.client.get(reverse('orders:checkout')), reverse('orders:cart'), fetch_redirect_response=False)

    def test_wishlist_still_works(self):
        self.login()
        self.client.post(reverse('wishlist:add', args=[self.phone.id]))
        self.assertTrue(Wishlist.objects.filter(user=self.alice, product=self.phone).exists())
        self.assertContains(self.client.get(reverse('wishlist:list')), 'Phone X')
        detail = self.client.get(self.phone.get_absolute_url())
        self.assertContains(detail, 'Saved to wishlist')
        self.client.post(reverse('wishlist:remove', args=[self.phone.id]))
        self.assertFalse(Wishlist.objects.exists())

    # --- product details page ------------------------------------------------
    def test_product_page_shows_variants_and_buy_now(self):
        self.login()
        resp = self.client.get(self.phone.get_absolute_url())
        self.assertContains(resp, 'Buy Now')
        self.assertContains(resp, 'Add to cart')
        self.assertContains(resp, reverse('orders:buy_now'))
        for name in ('Blue', 'Red', 'Gold'):
            self.assertContains(resp, name)
        self.assertContains(resp, '(Out of stock)')

    def test_in_stock_variants_are_listed_first(self):
        self.login()
        variants = self.client.get(self.phone.get_absolute_url()).context['variants']
        self.assertEqual([v.name for v in variants], ['Blue', 'Gold', 'Red'])

    def test_anonymous_product_page_buy_now_links_to_login(self):
        resp = self.client.get(self.phone.get_absolute_url())
        self.assertContains(resp, 'accounts/login/?next=')
        self.assertContains(resp, 'Buy Now')

    def test_product_page_queries_do_not_grow_with_reviews(self):
        def add_reviews(n, start):
            for i in range(start, start + n):
                u = User.objects.create_user(f'rev{i}', password='pw12345!')
                Review.objects.create(product=self.phone, customer=u, rating=4, comment='ok')
        add_reviews(1, 0)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.phone.get_absolute_url())
        add_reviews(6, 10)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.phone.get_absolute_url())
        self.assertEqual(len(few), len(many))


class SimpleVariant:
    """Stand-in carrying just an id, for posting bogus variant ids through buy()."""
    def __init__(self, id):
        self.id = id if id is not None else ''


# ======================= Phase 3: customer orders & tracking =======================

class CustomerOrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor_a = User.objects.create_user('vendA', password='pw12345!', role=User.Role.VENDOR)
        cls.vendor_b = User.objects.create_user('vendB', password='pw12345!', role=User.Role.VENDOR)
        VendorStore.objects.create(vendor=cls.vendor_a,store_name='Alpha Store',status=VendorStore.Status.APPROVED)
        VendorStore.objects.create(vendor=cls.vendor_b,store_name='Beta Store',status=VendorStore.Status.APPROVED)
        cls.alice = User.objects.create_user('alice', password='pw12345!')
        cls.bob = User.objects.create_user('bob', password='pw12345!')
        cls.addr = Address.objects.create(user=cls.alice, full_name='Alice A', phone='9', address_line='1 Main St',
                                          city='Pune', state='MH', pincode='411001')
        cls.pa = make_product(cls.vendor_a, 'Alpha Phone', 'AP')
        cls.pb = make_product(cls.vendor_b, 'Beta Case', 'BC')
        # Stock AFTER the (simulated) purchases below: 5 originally, 2 bought.
        cls.va = make_variant(cls.pa, 'Blue', 3, 'AP-BLUE')
        cls.vb = make_variant(cls.pb, 'Black', 3, 'BC-BLACK')
        cls.counter = 0

    def make_order(self, customer=None, lines=None, address=True):
        """lines: [(variant, quantity, vendor_order_status), ...]; one VendorOrder per vendor."""
        CustomerOrderTests.counter += 1
        customer = customer or self.alice
        lines = lines or [(self.va, 2, VendorOrder.Status.PENDING)]
        subtotal = sum(v.effective_price * q for v, q, _ in lines)
        order = Order.objects.create(
            order_number=f'ORD-T{self.counter:04d}', customer=customer,
            shipping_address=self.addr if address and customer == self.alice else None,
            subtotal=subtotal, tax_amount=Decimal('5.00'), shipping_charge=Decimal('50.00'),
            total_amount=subtotal + Decimal('55.00'),
        )
        by_vendor = {}
        for variant, qty, status in lines:
            by_vendor.setdefault((variant.product.vendor, status), []).append((variant, qty))
        for (vendor, status), items in by_vendor.items():
            vo = VendorOrder.objects.create(
                order=order, vendor=vendor, status=status,
                subtotal=sum(v.effective_price * q for v, q in items),
            )
            for variant, qty in items:
                OrderItem.objects.create(vendor_order=vo, variant=variant, product_name=variant.product.name,
                                         variant_name=variant.name, price=variant.effective_price, quantity=qty)
        return order

    def login(self, user=None):
        self.client.force_login(user or self.alice)

    def set_status(self, order, vendor, status):
        VendorOrder.objects.filter(order=order, vendor=vendor).update(status=status)

    # --- 1. My Orders ---------------------------------------------------------
    def test_my_orders_lists_only_own_orders(self):
        mine = self.make_order()
        theirs = self.make_order(customer=self.bob)
        self.login()
        resp = self.client.get(reverse('orders:order_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, mine.order_number)
        self.assertNotContains(resp, theirs.order_number)
        self.assertContains(resp, '₹215.00')  # 160 + 55
        self.assertContains(resp, 'Cash on Delivery')
        self.assertContains(resp, reverse('orders:order_track', args=[mine.order_number]))
        self.assertContains(resp, reverse('orders:order_detail', args=[mine.order_number]))
        self.assertContains(resp, 'Pending')

    def test_my_orders_requires_login(self):
        resp = self.client.get(reverse('orders:order_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_my_orders_status_summary_for_multi_vendor(self):
        self.make_order(lines=[(self.va, 1, VendorOrder.Status.SHIPPED), (self.vb, 1, VendorOrder.Status.PENDING)])
        self.login()
        self.assertContains(self.client.get(reverse('orders:order_list')), '1 Pending, 1 Shipped')

    def test_my_orders_pagination_preserved(self):
        for _ in range(12):
            self.make_order()
        self.login()
        first = self.client.get(reverse('orders:order_list'))
        self.assertEqual(len(first.context['orders']), 10)
        self.assertContains(first, 'Page 1 of 2')
        second = self.client.get(reverse('orders:order_list') + '?page=2')
        self.assertEqual(len(second.context['orders']), 2)

    def test_my_orders_query_count_does_not_grow(self):
        self.make_order()
        self.login()
        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse('orders:order_list'))
        for _ in range(7):
            self.make_order(lines=[(self.va, 1, VendorOrder.Status.PENDING), (self.vb, 1, VendorOrder.Status.SHIPPED)])
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse('orders:order_list'))
        self.assertEqual(len(one), len(many))

    # --- 2. Order details -----------------------------------------------------
    def test_order_detail_shows_everything(self):
        order = self.make_order(lines=[(self.va, 2, VendorOrder.Status.PENDING), (self.vb, 1, VendorOrder.Status.CONFIRMED)])
        self.login()
        resp = self.client.get(reverse('orders:order_detail', args=[order.order_number]))
        self.assertEqual(resp.status_code, 200)
        for text in (order.order_number, 'Alpha Store', 'Beta Store', 'Alpha Phone', 'Blue', 'Beta Case', 'Black',
                     '₹80.00', '₹160.00', 'Pending', 'Confirmed', 'Alice A', '1 Main St', 'Cash on Delivery',
                     'Track Order'):
            self.assertContains(resp, text)
        self.assertContains(resp, f"₹{order.total_amount}")

    def test_order_detail_without_address_does_not_crash(self):
        order = self.make_order(address=False)
        self.login()
        self.assertEqual(self.client.get(reverse('orders:order_detail', args=[order.order_number])).status_code, 200)

    def test_detail_and_track_query_counts_do_not_grow_with_vendors(self):
        order = self.make_order()
        self.login()
        with CaptureQueriesContext(connection) as d1:
            self.client.get(reverse('orders:order_detail', args=[order.order_number]))
        with CaptureQueriesContext(connection) as t1:
            self.client.get(reverse('orders:order_track', args=[order.order_number]))
        extra_vendors = []
        for i in range(3):
            v = User.objects.create_user(f'extraV{i}', password='pw12345!', role=User.Role.VENDOR)
            VendorStore.objects.create(vendor=v, store_name=f'Extra {i}')
            extra_vendors.append(make_variant(make_product(v, f'Extra P{i}', f'EX{i}'), 'Std', 3, f'EX{i}-S'))
        big = self.make_order(lines=[(self.va, 1, VendorOrder.Status.PENDING), (self.vb, 1, VendorOrder.Status.PACKED)]
                              + [(ev, 1, VendorOrder.Status.CONFIRMED) for ev in extra_vendors])
        with CaptureQueriesContext(connection) as d2:
            self.client.get(reverse('orders:order_detail', args=[big.order_number]))
        with CaptureQueriesContext(connection) as t2:
            self.client.get(reverse('orders:order_track', args=[big.order_number]))
        self.assertEqual(len(d1), len(d2))
        self.assertEqual(len(t1), len(t2))

    # --- 3-5. Tracking ----------------------------------------------------------
    def test_customer_can_open_tracking_for_own_order(self):
        order = self.make_order()
        self.login()
        resp = self.client.get(reverse('orders:order_track', args=[order.order_number]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Track Order')
        self.assertContains(resp, 'Order placed')
        self.assertNotContains(resp, '/admin/')

    def test_multi_vendor_tracking_shows_separate_statuses(self):
        order = self.make_order(lines=[(self.va, 1, VendorOrder.Status.SHIPPED), (self.vb, 1, VendorOrder.Status.PENDING)])
        self.login()
        resp = self.client.get(reverse('orders:order_track', args=[order.order_number]))
        by_store = {vo.vendor.store.store_name: vo.status for vo in resp.context['vendor_orders']}
        self.assertEqual(by_store, {'Alpha Store': 'shipped', 'Beta Store': 'pending'})
        a = next(vo for vo in resp.context['vendor_orders'] if vo.vendor_id == self.vendor_a.id)
        b = next(vo for vo in resp.context['vendor_orders'] if vo.vendor_id == self.vendor_b.id)
        self.assertEqual([s['state'] for s in a.timeline], ['done', 'done', 'done', 'done', 'current', 'todo'])
        self.assertEqual([s['state'] for s in b.timeline], ['current', 'todo', 'todo', 'todo', 'todo', 'todo'])

    def test_timeline_reflects_status_changes(self):
        order = self.make_order()
        self.login()
        url = reverse('orders:order_track', args=[order.order_number])
        expected = {
            'confirmed': ['done', 'current', 'todo', 'todo', 'todo', 'todo'],
            'processing': ['done', 'done', 'current', 'todo', 'todo', 'todo'],
            'packed': ['done', 'done', 'done', 'current', 'todo', 'todo'],
            'shipped': ['done', 'done', 'done', 'done', 'current', 'todo'],
            'delivered': ['done'] * 6,
        }
        for status, states in expected.items():
            self.set_status(order, self.vendor_a, status)
            vo = self.client.get(url).context['vendor_orders'][0]
            self.assertEqual([s['state'] for s in vo.timeline], states, status)

    def test_cancelled_returned_refunded_are_not_shown_as_active(self):
        order = self.make_order()
        self.login()
        url = reverse('orders:order_track', args=[order.order_number])
        for status, text in (('cancelled', 'was cancelled'), ('returned', 'delivered and then returned'),
                             ('refunded', 'returned and refunded')):
            self.set_status(order, self.vendor_a, status)
            resp = self.client.get(url)
            self.assertIsNone(resp.context['vendor_orders'][0].timeline)
            self.assertContains(resp, text)
            self.assertNotContains(resp, 'track-steps')
            self.assertNotContains(resp, 'Cancel this vendor')

    def test_build_timeline_unknown_state(self):
        self.assertIsNone(build_timeline('cancelled'))
        self.assertEqual(len(build_timeline('pending')), 6)

    # --- 6-7. Cancellation -------------------------------------------------------
    def cancel_url(self, order, vendor):
        return reverse('orders:cancel_vendor_order', args=[VendorOrder.objects.get(order=order, vendor=vendor).pk])

    def test_cancel_allowed_for_pending_and_confirmed_and_restocks(self):
        for status in ('pending', 'confirmed'):
            ProductVariant.objects.filter(pk=self.va.pk).update(stock_quantity=3)
            order = self.make_order(lines=[(self.va, 2, status)])
            self.login()
            resp = self.client.post(self.cancel_url(order, self.vendor_a))
            self.assertRedirects(resp, reverse('orders:order_detail', args=[order.order_number]), fetch_redirect_response=False)
            self.assertEqual(VendorOrder.objects.get(order=order).status, 'cancelled')
            self.va.refresh_from_db()
            self.assertEqual(self.va.stock_quantity, 5, status)

    def test_cancel_not_allowed_after_processing(self):
        for status in ('processing', 'packed', 'shipped', 'delivered', 'returned', 'refunded'):
            order = self.make_order(lines=[(self.va, 2, status)])
            self.login()
            self.client.post(self.cancel_url(order, self.vendor_a))
            self.assertEqual(VendorOrder.objects.get(order=order).status, status)
        self.va.refresh_from_db()
        self.assertEqual(self.va.stock_quantity, 3)

    def test_cancel_restores_stock_only_once(self):
        order = self.make_order(lines=[(self.va, 2, 'pending')])
        self.login()
        url = self.cancel_url(order, self.vendor_a)
        self.client.post(url)
        self.client.post(url)
        self.client.post(url)
        self.va.refresh_from_db()
        self.assertEqual(self.va.stock_quantity, 5)
        self.assertEqual(StockHistory.objects.filter(variant=self.va, change_quantity=2).count(), 1)

    def test_cancel_one_vendor_leaves_other_vendor_untouched(self):
        order = self.make_order(lines=[(self.va, 2, 'pending'), (self.vb, 1, 'pending')])
        self.login()
        self.client.post(self.cancel_url(order, self.vendor_a))
        self.assertEqual(VendorOrder.objects.get(order=order, vendor=self.vendor_a).status, 'cancelled')
        self.assertEqual(VendorOrder.objects.get(order=order, vendor=self.vendor_b).status, 'pending')
        self.vb.refresh_from_db()
        self.assertEqual(self.vb.stock_quantity, 3)

    def test_cancel_buttons_only_shown_when_allowed(self):
        order = self.make_order(lines=[(self.va, 1, 'pending'), (self.vb, 1, 'shipped')])
        self.login()
        vo_a = VendorOrder.objects.get(order=order, vendor=self.vendor_a)
        vo_b = VendorOrder.objects.get(order=order, vendor=self.vendor_b)
        for name in ('orders:order_detail', 'orders:order_track'):
            resp = self.client.get(reverse(name, args=[order.order_number]))
            self.assertContains(resp, reverse('orders:cancel_vendor_order', args=[vo_a.pk]))
            self.assertNotContains(resp, reverse('orders:cancel_vendor_order', args=[vo_b.pk]))

    def test_cancel_requires_post_and_csrf(self):
        order = self.make_order()
        url = self.cancel_url(order, self.vendor_a)
        self.login()
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(url).status_code, 403)
        self.assertEqual(VendorOrder.objects.get(order=order).status, 'pending')

    # --- 8. Isolation ------------------------------------------------------------
    def test_customer_cannot_view_another_customers_order(self):
        theirs = self.make_order(customer=self.bob)
        self.login()
        for name in ('orders:order_detail', 'orders:order_track'):
            self.assertEqual(self.client.get(reverse(name, args=[theirs.order_number])).status_code, 404)
        self.assertEqual(self.client.get(reverse('orders:order_detail', args=['ORD-DOESNOTEXIST'])).status_code, 404)

    def test_anonymous_cannot_open_order_pages(self):
        order = self.make_order()
        for name in ('orders:order_detail', 'orders:order_track'):
            resp = self.client.get(reverse(name, args=[order.order_number]))
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_customer_cannot_cancel_another_customers_vendor_order(self):
        theirs = self.make_order(customer=self.bob, lines=[(self.va, 2, 'pending')])
        self.login()
        resp = self.client.post(self.cancel_url(theirs, self.vendor_a))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(VendorOrder.objects.get(order=theirs).status, 'pending')
        self.va.refresh_from_db()
        self.assertEqual(self.va.stock_quantity, 3)

    def test_vendor_cannot_use_customer_cancel_on_customer_orders(self):
        order = self.make_order()
        self.client.force_login(self.vendor_a)
        resp = self.client.post(self.cancel_url(order, self.vendor_a))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(VendorOrder.objects.get(order=order).status, 'pending')

    # --- 9. Vendor pages remain vendor-only ---------------------------------------
    def test_vendor_order_pages_blocked_for_customers(self):
        order = self.make_order()
        vo = VendorOrder.objects.get(order=order)
        self.login()
        self.assertEqual(self.client.get(reverse('orders:vendor_order_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('orders:vendor_order_detail', args=[vo.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('orders:vendor_order_detail', args=[vo.pk]),
                                          {'status': 'confirmed'}).status_code, 403)
        self.assertEqual(VendorOrder.objects.get(pk=vo.pk).status, 'pending')

    def test_vendor_order_management_still_works_for_owner_only(self):
        order = self.make_order()
        vo = VendorOrder.objects.get(order=order)
        self.client.force_login(self.vendor_a)
        self.assertEqual(self.client.get(reverse('orders:vendor_order_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('orders:vendor_order_detail', args=[vo.pk])).status_code, 200)
        self.client.post(reverse('orders:vendor_order_detail', args=[vo.pk]), {'status': 'confirmed'})
        self.assertEqual(VendorOrder.objects.get(pk=vo.pk).status, 'confirmed')
        # the tracking page reflects the vendor's change
        self.login()
        resp = self.client.get(reverse('orders:order_track', args=[order.order_number]))
        self.assertEqual(resp.context['vendor_orders'][0].status, 'confirmed')
        # another vendor cannot touch it
        self.client.force_login(self.vendor_b)
        self.assertEqual(self.client.get(reverse('orders:vendor_order_detail', args=[vo.pk])).status_code, 404)

    def test_vendor_cancel_then_customer_cancel_does_not_restock_twice(self):
        order = self.make_order(lines=[(self.va, 2, 'pending')])
        vo = VendorOrder.objects.get(order=order)
        self.client.force_login(self.vendor_a)
        self.client.post(reverse('orders:vendor_order_detail', args=[vo.pk]), {'status': 'cancelled'})
        self.login()
        self.client.post(reverse('orders:cancel_vendor_order', args=[vo.pk]))
        self.va.refresh_from_db()
        self.assertEqual(self.va.stock_quantity, 5)
