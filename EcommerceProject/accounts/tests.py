from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from vendors.models import VendorStore

User = get_user_model()
R = User.Role
PW = 'pw12345!'


def make_user(username, role, **extra):
    return User.objects.create_user(username, password=PW, role=role, **extra)


def make_vendor(username, status=VendorStore.Status.APPROVED):
    user = make_user(username, R.VENDOR)
    VendorStore.objects.create(vendor=user, store_name=f'{username} store', status=status)
    return user


class RoleModelTests(TestCase):
    def test_exactly_four_roles(self):
        self.assertEqual([v for v, _ in R.choices], ['customer', 'vendor', 'admin', 'super_admin'])
        self.assertEqual([l for _, l in R.choices], ['Customer', 'Vendor', 'Admin', 'Super Admin'])

    def test_customer_and_vendor_are_never_staff_or_superuser(self):
        for role in (R.CUSTOMER, R.VENDOR):
            u = make_user(f'u_{role}', role, is_staff=True, is_superuser=True)
            u.refresh_from_db()
            self.assertFalse(u.is_staff)
            self.assertFalse(u.is_superuser)

    def test_admin_is_not_a_superuser(self):
        u = make_user('adm', R.ADMIN, is_superuser=True)
        u.refresh_from_db()
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.is_admin_role)
        self.assertFalse(u.is_super_admin_role)

    def test_super_admin_is_staff_and_superuser(self):
        u = make_user('sa', R.SUPER_ADMIN)
        u.refresh_from_db()
        self.assertTrue(u.is_staff and u.is_superuser)
        self.assertTrue(u.is_admin_role and u.is_super_admin_role)

    def test_createsuperuser_gets_super_admin_role(self):
        u = User.objects.create_superuser('root', 'r@example.com', PW)
        self.assertEqual(u.role, R.SUPER_ADMIN)
        self.assertTrue(u.is_superuser)

    def test_role_predicates_are_exclusive(self):
        for role, expected in ((R.CUSTOMER, 'is_customer_role'), (R.VENDOR, 'is_vendor_role'),
                               (R.ADMIN, 'is_admin_role'), (R.SUPER_ADMIN, 'is_super_admin_role')):
            u = make_user(f'x_{role}', role)
            self.assertTrue(getattr(u, expected))
            if role in (R.ADMIN, R.SUPER_ADMIN):
                self.assertFalse(u.is_customer_role or u.is_vendor_role)
            else:
                self.assertFalse(u.is_admin_role or u.is_super_admin_role)

    def test_role_changes_update_flags(self):
        u = make_user('chg', R.CUSTOMER)
        u.role = R.SUPER_ADMIN
        u.save()
        u.refresh_from_db()
        self.assertTrue(u.is_staff and u.is_superuser)
        u.role = R.ADMIN
        u.save()
        u.refresh_from_db()
        self.assertFalse(u.is_superuser)
        u.role = R.VENDOR
        u.save()
        u.refresh_from_db()
        self.assertFalse(u.is_staff or u.is_superuser)

    def test_save_with_update_fields_still_syncs_flags(self):
        u = make_user('uf', R.CUSTOMER)
        User.objects.filter(pk=u.pk).update(is_staff=True)  # bulk update bypasses save()
        u = User.objects.get(pk=u.pk)
        u.save(update_fields=['last_login'])
        u.refresh_from_db()
        self.assertFalse(u.is_staff)

    def test_registration_only_offers_customer_and_vendor(self):
        resp = self.client.post(reverse('accounts:register'), {
            'username': 'sneaky', 'email': 's@example.com', 'role': 'super_admin',
            'password1': 'Str0ng!Pass99', 'password2': 'Str0ng!Pass99'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username='sneaky').exists())

    def test_profile_form_cannot_change_role(self):
        u = make_user('prof', R.CUSTOMER)
        self.client.force_login(u)
        self.client.post(reverse('accounts:profile'), {
            'first_name': 'A', 'last_name': 'B', 'email': 'a@b.com', 'mobile_number': '1',
            'role': 'super_admin', 'is_superuser': 'on', 'is_staff': 'on'})
        u.refresh_from_db()
        self.assertEqual(u.role, R.CUSTOMER)
        self.assertFalse(u.is_staff or u.is_superuser)

    def test_existing_groups_are_untouched_by_role_changes(self):
        group = Group.objects.create(name='Catalog Editors')
        u = make_user('grp', R.ADMIN)
        u.groups.add(group)
        u.role = R.CUSTOMER
        u.save()
        self.assertTrue(u.groups.filter(name='Catalog Editors').exists())


class RoleAccessTests(TestCase):
    """What each role can and cannot reach."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = make_user('cust', R.CUSTOMER)
        cls.vendor = make_vendor('vend')
        cls.pending_vendor = make_vendor('pendv', VendorStore.Status.PENDING)
        cls.admin = make_user('adm', R.ADMIN)
        cls.staff_admin = make_user('staffadm', R.ADMIN, is_staff=True)
        cls.super_admin = make_user('sa', R.SUPER_ADMIN)
        cls.admin_dash = reverse('dashboard:admin_dashboard')
        cls.vendor_dash = reverse('vendors:dashboard')
        cls.customer_dash = reverse('dashboard:customer_dashboard')
        cls.admin_urls = [
            cls.admin_dash,
            reverse('dashboard:approve_vendor', args=[1]),
            reverse('dashboard:reject_vendor', args=[1]),
            reverse('dashboard:approve_product', args=[1]),
            reverse('dashboard:reject_product', args=[1]),
        ]
        cls.vendor_urls = [cls.vendor_dash, reverse('vendors:store_settings'),
                           reverse('catalog:vendor_product_list')]

    def _login(self, user):
        self.client.force_login(user)

    def _redirect_target(self, user):
        self._login(user)
        return self.client.get(reverse('dashboard:redirect'))['Location']

    def _in_django_admin(self):
        return self.client.get(reverse('admin:index')).status_code == 200

    # ---- post-login routing ----
    def test_each_role_lands_on_its_own_dashboard(self):
        self.assertEqual(self._redirect_target(self.customer), self.customer_dash)
        self.assertEqual(self._redirect_target(self.vendor), self.vendor_dash)
        self.assertEqual(self._redirect_target(self.admin), self.admin_dash)
        self.assertEqual(self._redirect_target(self.super_admin), self.admin_dash)

    # ---- customer ----
    def test_customer_dashboard_ok(self):
        self._login(self.customer)
        self.assertEqual(self.client.get(self.customer_dash).status_code, 200)

    def test_customer_blocked_from_admin_vendor_and_django_admin(self):
        self._login(self.customer)
        for url in self.admin_urls + self.vendor_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertFalse(self._in_django_admin())

    # ---- vendor ----
    def test_approved_vendor_dashboard_ok(self):
        self._login(self.vendor)
        self.assertEqual(self.client.get(self.vendor_dash).status_code, 200)

    def test_vendor_blocked_from_admin_urls_and_django_admin(self):
        self._login(self.vendor)
        for url in self.admin_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertFalse(self._in_django_admin())

    def test_vendor_is_sent_away_from_customer_dashboard(self):
        self._login(self.vendor)
        resp = self.client.get(self.customer_dash)
        self.assertRedirects(resp, reverse('dashboard:redirect'), fetch_redirect_response=False)

    def test_pending_vendor_still_blocked(self):
        self._login(self.pending_vendor)
        self.assertRedirects(self.client.get(self.vendor_dash), reverse('vendors:access_status'),
                             fetch_redirect_response=False)

    # ---- admin ----
    def test_admin_dashboard_ok_but_not_vendor_pages(self):
        self._login(self.admin)
        self.assertEqual(self.client.get(self.admin_dash).status_code, 200)
        for url in self.vendor_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_without_staff_flag_cannot_use_django_admin(self):
        self._login(self.admin)
        self.assertFalse(self._in_django_admin())

    def test_admin_with_staff_flag_can_enter_django_admin_but_is_not_superuser(self):
        self._login(self.staff_admin)
        self.assertTrue(self._in_django_admin())
        self.assertFalse(self.staff_admin.is_superuser)
        # no permissions via Groups yet -> cannot see/change users
        self.assertEqual(self.client.get(reverse('admin:accounts_user_changelist')).status_code, 403)

    def test_admin_can_approve_vendor(self):
        # Approval is a state change, so it is POST-only (a GET must never approve).
        self._login(self.admin)
        store = self.pending_vendor.store
        self.client.post(reverse('dashboard:approve_vendor', args=[store.pk]))
        store.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.APPROVED)

    def test_get_never_changes_approval_state(self):
        self._login(self.admin)
        store = self.pending_vendor.store
        for name in ('approve_vendor', 'reject_vendor'):
            self.assertEqual(self.client.get(reverse(f'dashboard:{name}', args=[store.pk])).status_code, 405)
        store.refresh_from_db()
        self.assertEqual(store.status, VendorStore.Status.PENDING)

    # ---- super admin ----
    def test_super_admin_full_access(self):
        self._login(self.super_admin)
        self.assertEqual(self.client.get(self.admin_dash).status_code, 200)
        self.assertTrue(self._in_django_admin())
        self.assertEqual(self.client.get(reverse('admin:accounts_user_changelist')).status_code, 200)
        for url in self.vendor_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_bulk_set_is_staff_on_customer_or_vendor_still_blocked_from_django_admin(self):
        User.objects.filter(pk__in=[self.customer.pk, self.vendor.pk]).update(is_staff=True)
        for user in (User.objects.get(pk=self.customer.pk), User.objects.get(pk=self.vendor.pk)):
            self._login(user)
            self.assertFalse(self._in_django_admin())

    # ---- anonymous ----
    def test_anonymous_redirected_to_login(self):
        for url in self.admin_urls + self.vendor_urls + [self.customer_dash]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 302)
                self.assertIn(reverse('accounts:login'), resp['Location'])
        resp = self.client.get(reverse('admin:index'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])

    # ---- role changes take effect immediately ----
    def test_role_change_changes_access(self):
        user = make_user('mover', R.CUSTOMER)
        self._login(user)
        self.assertEqual(self.client.get(self.admin_dash).status_code, 403)
        user.role = R.ADMIN
        user.save()
        self.assertEqual(self.client.get(self.admin_dash).status_code, 200)
        user.role = R.CUSTOMER
        user.save()
        self.assertEqual(self.client.get(self.admin_dash).status_code, 403)

    def test_demoted_super_admin_loses_django_admin(self):
        user = make_user('demote', R.SUPER_ADMIN)
        self._login(user)
        self.assertTrue(self._in_django_admin())
        user.role = R.VENDOR
        user.save()
        self.assertFalse(self._in_django_admin())


class UserAdminRoleTests(TestCase):
    """Role selection on the Django Admin user pages."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = make_user('sa', R.SUPER_ADMIN)
        cls.target = make_user('target', R.CUSTOMER)
        cls.staff_admin = make_user('staffadm', R.ADMIN, is_staff=True)
        group = Group.objects.create(name='Vendor Managers')
        from django.contrib.auth.models import Permission
        cls.staff_admin.groups.add(group)
        group.permissions.set(Permission.objects.filter(content_type__app_label='accounts',
                                                        content_type__model='user'))

    def _post_data(self, user, **over):
        data = {'username': user.username, 'role': user.role, 'first_name': '', 'last_name': '',
                'email': '', 'mobile_number': '', 'is_active': 'on', 'is_active_account': 'on',
                'is_staff': 'on' if user.is_staff else '',
                'last_login_0': '', 'last_login_1': '', 'date_joined_0': '2026-01-01', 'date_joined_1': '00:00:00',
                'initial-date_joined_0': '2026-01-01', 'initial-date_joined_1': '00:00:00'}
        data = {k: v for k, v in data.items() if v != ''}
        data.update(over)
        return data

    def test_role_field_is_on_edit_page_with_four_choices(self):
        self.client.force_login(self.super_admin)
        resp = self.client.get(reverse('admin:accounts_user_change', args=[self.target.pk]))
        self.assertContains(resp, 'name="role"')
        for label in ('Customer', 'Vendor', 'Admin', 'Super Admin'):
            self.assertContains(resp, f'>{label}</option>')

    def test_role_field_is_on_add_page(self):
        self.client.force_login(self.super_admin)
        self.assertContains(self.client.get(reverse('admin:accounts_user_add')), 'name="role"')

    def test_super_admin_can_change_role_in_django_admin(self):
        self.client.force_login(self.super_admin)
        resp = self.client.post(reverse('admin:accounts_user_change', args=[self.target.pk]),
                                self._post_data(self.target, role=R.ADMIN))
        self.assertEqual(resp.status_code, 302, getattr(resp, 'context', None) and resp.context['adminform'].form.errors)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, R.ADMIN)
        self.assertFalse(self.target.is_superuser)

    def test_super_admin_can_promote_to_super_admin(self):
        self.client.force_login(self.super_admin)
        self.client.post(reverse('admin:accounts_user_change', args=[self.target.pk]),
                         self._post_data(self.target, role=R.SUPER_ADMIN))
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, R.SUPER_ADMIN)
        self.assertTrue(self.target.is_staff and self.target.is_superuser)

    def test_staff_admin_cannot_grant_super_admin(self):
        self.client.force_login(self.staff_admin)
        resp = self.client.get(reverse('admin:accounts_user_change', args=[self.target.pk]))
        self.assertNotContains(resp, '>Super Admin</option>')
        self.client.post(reverse('admin:accounts_user_change', args=[self.target.pk]),
                         self._post_data(self.target, role=R.SUPER_ADMIN))
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, R.CUSTOMER)

    def test_staff_admin_cannot_edit_a_super_admin(self):
        self.client.force_login(self.staff_admin)
        resp = self.client.get(reverse('admin:accounts_user_change', args=[self.super_admin.pk]))
        self.assertEqual(resp.status_code, 403)
