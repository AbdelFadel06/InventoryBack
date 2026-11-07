"""
Photographie des droits ACTUELS de l'API, rôle par rôle.

Ces tests ne disent pas ce qui est souhaitable : ils décrivent ce que fait le code
aujourd'hui, pour détecter tout changement involontaire pendant la refonte des
permissions. Modifier une attente ici doit donc être une décision explicite.

Une case « autorisée » exige un statut 2xx : la requête doit aller au bout, sinon
un contrôle de rôle placé après la validation du corps resterait invisible.

Lancer : python manage.py test apps.accounts.test_permissions_baseline
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.inventories.models import Inventory, InventoryLine
from apps.products.models import Category, Product
from apps.sales.models import CashierSession, Expense, Sale
from apps.shops.models import Shop
from apps.stocks.models import Stock

User = get_user_model()

ADMIN = 'admin'
MANAGER = 'manager'
EMPLOYEE = 'employee'
LIVREUR = 'livreur'
MAGASINIER = 'magasinier'

ALL = {ADMIN, MANAGER, EMPLOYEE, LIVREUR, MAGASINIER}
ADMIN_ONLY = {ADMIN}
ADMIN_MANAGER = {ADMIN, MANAGER}
STOCK_WRITERS = {ADMIN, MANAGER, MAGASINIER}


def make_user(email, role, shop=None):
    return User.objects.create_user(
        username=email.split('@')[0],
        email=email,
        password='Str0ng-Passw0rd!',
        first_name=email.split('@')[0],
        last_name='Test',
        role=role,
        shop=shop,
    )


class PermissionFixtures(APITestCase):
    """Deux boutiques, et un utilisateur de chaque rôle dans la boutique A."""

    @classmethod
    def setUpTestData(cls):
        cls.shop_a = Shop.objects.create(name='Boutique A')
        cls.shop_b = Shop.objects.create(name='Boutique B')

        cls.admin = make_user('admin@test.local', 'SUPER_ADMIN')
        cls.manager = make_user('manager@test.local', 'SHOP_MANAGER', cls.shop_a)
        cls.employee = make_user('employee@test.local', 'EMPLOYEE', cls.shop_a)
        cls.livreur = make_user('livreur@test.local', 'LIVREUR', cls.shop_a)
        cls.magasinier = make_user('magasinier@test.local', 'MAGASINIER', cls.shop_a)
        cls.manager_b = make_user('manager-b@test.local', 'SHOP_MANAGER', cls.shop_b)
        cls.employee_b = make_user('employee-b@test.local', 'EMPLOYEE', cls.shop_b)
        cls.target = make_user('target@test.local', 'EMPLOYEE', cls.shop_a)

        cls.shop_a.managers.add(cls.manager)
        cls.shop_b.managers.add(cls.manager_b)

        cls.category = Category.objects.create(name='Catégorie A', shop=cls.shop_a)
        cls.product = Product.objects.create(
            name='Produit A', sku='SKU-A', category=cls.category,
            selling_price=1000, shop=cls.shop_a,
        )
        cls.product_without_stock = Product.objects.create(
            name='Produit sans stock', sku='SKU-EMPTY', category=cls.category,
            selling_price=500, shop=cls.shop_a,
        )
        cls.stock = Stock.objects.create(
            product=cls.product, shop=cls.shop_a, location='MAGASIN', quantity=10,
        )
        cls.session = CashierSession.objects.create(
            shop=cls.shop_a, cashier=cls.employee, created_by=cls.manager,
            start_date=date.today(), end_date=date.today(),
        )
        cls.sale = Sale.objects.create(
            shop=cls.shop_a, cashier=cls.employee, session=cls.session,
            sale_type='delivery', livreur=cls.livreur, total_amount=1000,
            payment_method='on_delivery', payment_status='pending',
        )
        cls.expense = Expense.objects.create(
            session=cls.session, shop=cls.shop_a, label='Dépense A', amount=100,
            created_by=cls.manager, sale_date=date.today(),
        )
        cls.inventory = Inventory.objects.create(
            reference='INV-EN-COURS',
            shop=cls.shop_a, inventory_date=date.today(), created_by=cls.manager,
            status='in_progress',
        )
        cls.line = InventoryLine.objects.create(
            inventory=cls.inventory, product=cls.product, expected_quantity=10,
        )
        cls.completed_inventory = Inventory.objects.create(
            reference='INV-TERMINE',
            shop=cls.shop_a, inventory_date=date.today(), created_by=cls.manager,
            status='completed',
        )

    def setUp(self):
        # Le compteur anti-abus (throttle) persiste entre les tests sinon.
        cache.clear()

    def call(self, user, method, url, data=None, **extra):
        self.client.force_authenticate(user)
        return getattr(self.client, method)(url, data, format='json', **extra)


class RoleMatrixTests(PermissionFixtures):
    """Les méthodes test_* sont générées à partir de MATRIX, une par couple (action, rôle)."""

    def check_cell(self, role, allowed, method, build_url, build_data):
        user = getattr(self, role)
        response = self.call(user, method, build_url(self), build_data(self))
        self.assertNotEqual(response.status_code, 405, 'Route ou méthode incorrecte dans la matrice')
        if allowed:
            self.assertTrue(
                200 <= response.status_code < 300,
                f'{role} devrait réussir : {response.status_code} {response.content[:200]}',
            )
        else:
            self.assertIn(
                response.status_code, (403, 404),
                f'{role} devrait être refusé : {response.status_code} {response.content[:200]}',
            )


def no_data(t):
    return None


# (nom, méthode, url, corps, rôles autorisés)
MATRIX = [
    # ── Utilisateurs ─────────────────────────────────────────────────
    ('users_list', 'get', lambda t: '/api/users/', no_data, ALL),
    ('users_create', 'post', lambda t: '/api/users/', lambda t: {
        'email': 'new@test.local', 'password': 'Str0ng-Passw0rd!',
        'password_confirm': 'Str0ng-Passw0rd!', 'first_name': 'New', 'last_name': 'User',
        'role': 'EMPLOYEE', 'shop': t.shop_a.id,
    }, ADMIN_MANAGER),
    ('users_update', 'patch', lambda t: f'/api/users/{t.target.id}/',
     lambda t: {'first_name': 'Renamed'}, ADMIN_MANAGER),
    ('users_delete', 'delete', lambda t: f'/api/users/{t.target.id}/', no_data, ADMIN_MANAGER),
    ('users_toggle_active', 'post', lambda t: f'/api/users/{t.target.id}/toggle_active/', no_data, ADMIN_MANAGER),

    # ── Boutiques ────────────────────────────────────────────────────
    ('shops_list', 'get', lambda t: '/api/shops/', no_data, ALL),
    ('shops_create', 'post', lambda t: '/api/shops/', lambda t: {'name': 'Nouvelle'}, ADMIN_ONLY),
    ('shops_update', 'patch', lambda t: f'/api/shops/{t.shop_a.id}/', lambda t: {'city': 'Cotonou'}, ADMIN_ONLY),
    ('shops_delete', 'delete', lambda t: f'/api/shops/{t.shop_b.id}/', no_data, ADMIN_ONLY),
    ('shops_assign_manager', 'post', lambda t: f'/api/shops/{t.shop_a.id}/assign_manager/',
     lambda t: {'manager_id': t.manager_b.id}, ADMIN_ONLY),
    ('shops_assign_employees', 'post', lambda t: f'/api/shops/{t.shop_a.id}/assign_employees/',
     lambda t: {'user_ids': [t.target.id], 'start_date': date.today().isoformat()}, ADMIN_MANAGER),

    # ── Produits et catégories ───────────────────────────────────────
    ('products_list', 'get', lambda t: '/api/products/', no_data, ALL),
    ('products_create', 'post', lambda t: '/api/products/',
     lambda t: {'name': 'Nouveau', 'selling_price': '500'}, ADMIN_MANAGER),
    ('products_update', 'patch', lambda t: f'/api/products/{t.product.id}/',
     lambda t: {'name': 'Renommé'}, ADMIN_MANAGER),
    ('products_delete', 'delete', lambda t: f'/api/products/{t.product_without_stock.id}/', no_data, ADMIN_MANAGER),
    ('products_bulk_update_prices', 'post', lambda t: '/api/products/bulk_update_prices/',
     lambda t: {'product_ids': [t.product.id], 'percentage_increase': 10}, ADMIN_ONLY),
    ('categories_create', 'post', lambda t: '/api/categories/', lambda t: {'name': 'Nouvelle'}, ADMIN_MANAGER),

    # ── Stocks ───────────────────────────────────────────────────────
    ('stocks_list', 'get', lambda t: '/api/stocks/', no_data, ALL),
    ('stocks_adjust', 'post', lambda t: '/api/stocks/adjust/',
     lambda t: {'product': t.product.id, 'shop': t.shop_a.id, 'location': 'MAGASIN',
                'new_quantity': 5, 'reason': 'test'}, STOCK_WRITERS),
    ('stocks_adjust_boutique', 'post', lambda t: '/api/stocks/adjust/',
     lambda t: {'product': t.product.id, 'shop': t.shop_a.id, 'location': 'BOUTIQUE',
                'new_quantity': 5, 'reason': 'test'}, ADMIN_MANAGER),
    ('movements_add_stock', 'post', lambda t: '/api/stock-movements/add_stock/',
     lambda t: {'product': t.product.id, 'shop': t.shop_a.id, 'quantity': 1}, ALL),
    ('movements_remove_stock', 'post', lambda t: '/api/stock-movements/remove_stock/',
     lambda t: {'product': t.product.id, 'shop': t.shop_a.id, 'location': 'MAGASIN', 'quantity': 1}, ALL),
    ('transfers_create', 'post', lambda t: '/api/stock-transfers/', lambda t: {
        'transfer_type': 'warehouse', 'from_shop': t.shop_a.id, 'to_shop': t.shop_a.id,
        'product': t.product.id, 'quantity': 1,
    }, STOCK_WRITERS),

    # ── Inventaires ──────────────────────────────────────────────────
    ('inventories_list', 'get', lambda t: '/api/inventories/', no_data, ALL),
    ('inventories_create', 'post', lambda t: '/api/inventories/',
     lambda t: {'shop': t.shop_a.id, 'inventory_date': timezone.now().date().isoformat()}, ADMIN_MANAGER),
    ('inventories_count', 'post', lambda t: f'/api/inventories/{t.inventory.id}/count_product/',
     lambda t: {'line_id': t.line.id, 'counted_quantity': 9}, ALL),
    ('inventories_validate', 'post', lambda t: f'/api/inventories/{t.completed_inventory.id}/validate/',
     no_data, ADMIN_MANAGER),
    ('inventories_cancel', 'post', lambda t: f'/api/inventories/{t.inventory.id}/cancel/',
     no_data, {ADMIN, MANAGER, LIVREUR, MAGASINIER}),

    # ── Ventes, caisse et dépenses ───────────────────────────────────
    ('sales_list', 'get', lambda t: '/api/sales/?all=true', no_data, ALL),
    ('sales_daily_report', 'get', lambda t: '/api/sales/daily_report/', no_data, ALL),
    ('sales_cancel', 'post', lambda t: f'/api/sales/{t.sale.id}/cancel/', no_data, ALL),
    ('sales_mark_delivered', 'post', lambda t: f'/api/sales/{t.sale.id}/mark_delivered/', no_data, ALL),
    ('sales_validate_payment', 'post', lambda t: f'/api/sales/{t.sale.id}/validate_payment/', no_data, ALL),
    ('sales_mark_livreur_paid', 'post', lambda t: f'/api/sales/{t.sale.id}/mark_livreur_paid/', no_data, ALL),
    ('sessions_create', 'post', lambda t: '/api/cashier-sessions/', lambda t: {
        'shop': t.shop_a.id, 'cashier': t.target.id, 'period_type': 'daily',
        'start_date': (date.today() + timedelta(days=30)).isoformat(),
        'end_date': (date.today() + timedelta(days=30)).isoformat(),
    }, ALL),
    ('sessions_close', 'post', lambda t: f'/api/cashier-sessions/{t.session.id}/close/', no_data, ALL),
    ('sessions_delete', 'delete', lambda t: f'/api/cashier-sessions/{t.session.id}/', no_data, ALL),
    ('expenses_create', 'post', lambda t: '/api/expenses/', lambda t: {
        'session': t.session.id, 'label': 'Transport', 'amount': '500',
        'sale_date': date.today().isoformat(),
    }, ALL),
    ('expenses_delete', 'delete', lambda t: f'/api/expenses/{t.expense.id}/', no_data, ALL),
]

# Ces cases plantent aujourd'hui (erreur 500) : voir KnownFlawTests.
CRASHING_CELLS = {
    ('products_bulk_update_prices', ADMIN),
    ('expenses_create', ADMIN),
}


def _add_matrix_tests():
    for name, method, build_url, build_data, allowed_roles in MATRIX:
        for role in sorted(ALL):
            if (name, role) in CRASHING_CELLS:
                continue
            def test(self, role=role, allowed=role in allowed_roles,
                     method=method, build_url=build_url, build_data=build_data):
                self.check_cell(role, allowed, method, build_url, build_data)
            verdict = 'allowed' if role in allowed_roles else 'denied'
            setattr(RoleMatrixTests, f'test_{name}__{role}__{verdict}', test)


_add_matrix_tests()


class ShopIsolationTests(PermissionFixtures):
    """Les données d'une boutique restent invisibles depuis une autre."""

    def test_manager_b_cannot_update_employee_of_shop_a(self):
        response = self.call(self.manager_b, 'patch', f'/api/users/{self.target.id}/', {'first_name': 'X'})
        self.assertIn(response.status_code, (403, 404))

    def test_manager_b_cannot_read_product_of_shop_a(self):
        response = self.call(self.manager_b, 'get', f'/api/products/{self.product.id}/')
        self.assertEqual(response.status_code, 404)

    def test_employee_b_cannot_read_product_of_shop_a(self):
        response = self.call(self.employee_b, 'get', f'/api/products/{self.product.id}/')
        self.assertEqual(response.status_code, 404)

    def test_manager_b_cannot_cancel_sale_of_shop_a(self):
        response = self.call(self.manager_b, 'post', f'/api/sales/{self.sale.id}/cancel/')
        self.assertEqual(response.status_code, 404)

    def test_forged_active_shop_header_does_not_open_shop_a(self):
        response = self.call(
            self.manager_b, 'post', f'/api/sales/{self.sale.id}/cancel/',
            HTTP_X_ACTIVE_SHOP=str(self.shop_a.id),
        )
        self.assertEqual(response.status_code, 404)
        self.sale.refresh_from_db()
        self.assertNotEqual(self.sale.status, 'cancelled')


class KnownFlawTests(PermissionFixtures):
    """
    Défauts connus, épinglés tels qu'ils existent aujourd'hui.

    Chaque test RÉUSSIT tant que le défaut existe. Quand il sera corrigé, le test
    échouera : il faudra alors inverser son attente.
    """

    def test_FLAW_employee_can_cancel_a_sale_and_restock(self):
        response = self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/cancel/')
        self.assertEqual(response.status_code, 200, response.content)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, 'cancelled')

    def test_FLAW_magasinier_can_delete_a_cashier_session(self):
        session_id = self.session.id
        response = self.call(self.magasinier, 'delete', f'/api/cashier-sessions/{session_id}/')
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(CashierSession.objects.filter(id=session_id).exists())

    def test_FLAW_employee_can_add_stock(self):
        response = self.call(self.employee, 'post', '/api/stock-movements/add_stock/', {
            'product': self.product.id, 'shop': self.shop_a.id, 'location': 'MAGASIN', 'quantity': 5,
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 15)

    def test_FLAW_multi_shop_manager_gets_403_on_stock_of_active_shop(self):
        """Le queryset suit la boutique active, mais le contrôle objet suit user.shop."""
        self.shop_b.managers.add(self.manager)
        stock_b = Stock.objects.create(
            product=self.product, shop=self.shop_b, location='MAGASIN', quantity=3,
        )
        response = self.call(
            self.manager, 'get', f'/api/stocks/{stock_b.id}/',
            HTTP_X_ACTIVE_SHOP=str(self.shop_b.id),
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_FLAW_bulk_update_prices_crashes(self):
        with self.assertRaises(TypeError):
            self.call(self.admin, 'post', '/api/products/bulk_update_prices/', {
                'product_ids': [self.product.id], 'percentage_increase': 10,
            })

    def test_FLAW_super_admin_expense_crashes_because_it_has_no_shop(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.call(self.admin, 'post', '/api/expenses/', {
                'session': self.session.id, 'label': 'Transport', 'amount': '500',
                'sale_date': date.today().isoformat(),
            })

    def test_FLAW_inventory_of_today_is_refused_between_midnight_and_1am(self):
        """00 h 30 à Porto-Novo : la date locale est le 2, mais la comparaison se fait en UTC (le 1er)."""
        just_after_local_midnight = datetime(2026, 1, 1, 23, 30, tzinfo=dt_timezone.utc)
        with patch('apps.inventories.serializers.inventory.timezone.now', return_value=just_after_local_midnight):
            response = self.call(self.manager, 'post', '/api/inventories/', {
                'shop': self.shop_a.id, 'inventory_date': '2026-01-02',
            })
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('inventory_date', response.json())
