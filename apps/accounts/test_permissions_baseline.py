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
NOT_WAREHOUSE = {ADMIN, MANAGER, EMPLOYEE, LIVREUR}
BOUTIQUE_FIGURES = {ADMIN, MANAGER, EMPLOYEE}
# Le manager et le caissier de la session active (ici `employee`) tiennent la caisse.
REGISTER = {MANAGER, EMPLOYEE}


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
        cls.boutique_stock = Stock.objects.create(
            product=cls.product, shop=cls.shop_a, location='BOUTIQUE', quantity=10,
        )
        # L'employé `employee` est le caissier du jour, `target` est un employé ordinaire.
        cls.session = CashierSession.objects.create(
            shop=cls.shop_a, cashier=cls.employee, created_by=cls.manager,
            start_date=date.today(), end_date=date.today(),
        )
        cls.past_empty_session = CashierSession.objects.create(
            shop=cls.shop_a, cashier=cls.employee, created_by=cls.manager,
            start_date=date.today() - timedelta(days=5), end_date=date.today() - timedelta(days=5),
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
        cls.counted_inventory = Inventory.objects.create(
            reference='INV-COMPTE',
            shop=cls.shop_a, inventory_date=date.today(), created_by=cls.manager,
            status='in_progress',
        )
        InventoryLine.objects.create(
            inventory=cls.counted_inventory, product=cls.product,
            expected_quantity=10, counted_quantity=10,
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
     lambda t: {'product': t.product.id, 'shop': t.shop_a.id, 'quantity': 1}, STOCK_WRITERS),
    ('movements_remove_stock', 'post', lambda t: '/api/stock-movements/remove_stock/',
     lambda t: {'product': t.product.id, 'shop': t.shop_a.id, 'location': 'MAGASIN', 'quantity': 1}, STOCK_WRITERS),
    ('transfers_create', 'post', lambda t: '/api/stock-transfers/', lambda t: {
        'transfer_type': 'warehouse', 'from_shop': t.shop_a.id, 'to_shop': t.shop_a.id,
        'product': t.product.id, 'quantity': 1,
    }, STOCK_WRITERS),

    # ── Inventaires ──────────────────────────────────────────────────
    ('inventories_list', 'get', lambda t: '/api/inventories/', no_data, ALL),
    ('inventories_create', 'post', lambda t: '/api/inventories/',
     lambda t: {'shop': t.shop_a.id, 'inventory_date': timezone.localdate().isoformat()}, ADMIN_MANAGER),
    ('inventories_count', 'post', lambda t: f'/api/inventories/{t.inventory.id}/count_product/',
     lambda t: {'line_id': t.line.id, 'counted_quantity': 9}, ALL),
    ('inventories_validate', 'post', lambda t: f'/api/inventories/{t.completed_inventory.id}/validate/',
     no_data, ADMIN_MANAGER),
    ('inventories_cancel', 'post', lambda t: f'/api/inventories/{t.inventory.id}/cancel/',
     no_data, ADMIN_MANAGER),
    ('inventories_delete', 'delete', lambda t: f'/api/inventories/{t.inventory.id}/',
     no_data, ADMIN_MANAGER),
    ('inventories_complete', 'post', lambda t: f'/api/inventories/{t.counted_inventory.id}/complete/',
     no_data, ADMIN_MANAGER),

    # ── Ventes, caisse et dépenses ───────────────────────────────────
    ('sales_list', 'get', lambda t: '/api/sales/?all=true', no_data, NOT_WAREHOUSE),
    ('sales_daily_report', 'get', lambda t: '/api/sales/daily_report/', no_data, BOUTIQUE_FIGURES),
    ('sales_period_report', 'get', lambda t: (
        f'/api/sales/period_report/?date_from={date.today().isoformat()}&date_to={date.today().isoformat()}'
    ), no_data, BOUTIQUE_FIGURES),
    ('sales_monthly_summary', 'get', lambda t: (
        f'/api/sales/monthly_summary/?year={date.today().year}&month={date.today().month}'
    ), no_data, BOUTIQUE_FIGURES),
    ('sales_livreur_stats', 'get', lambda t: '/api/sales/livreur_stats/', no_data, BOUTIQUE_FIGURES),
    ('sales_livreur_point', 'get', lambda t: '/api/sales/livreur_point/', no_data, NOT_WAREHOUSE),
    ('sales_create', 'post', lambda t: '/api/sales/', lambda t: {
        'items': [{'product': t.product.id, 'quantity': 1}],
    }, REGISTER),
    ('sales_cancel', 'post', lambda t: f'/api/sales/{t.sale.id}/cancel/',
     lambda t: {'reason': 'Erreur de saisie'}, ADMIN_MANAGER),
    ('sales_modify_items', 'post', lambda t: f'/api/sales/{t.sale.id}/modify_items/',
     lambda t: {'items': [{'product_id': t.product.id, 'quantity': 1}]}, {ADMIN, MANAGER, EMPLOYEE}),
    ('sales_mark_delivered', 'post', lambda t: f'/api/sales/{t.sale.id}/mark_delivered/', no_data, {LIVREUR}),
    ('sales_validate_payment', 'post', lambda t: f'/api/sales/{t.sale.id}/validate_payment/', no_data, REGISTER),
    ('sales_mark_livreur_paid', 'post', lambda t: f'/api/sales/{t.sale.id}/mark_livreur_paid/',
     no_data, ADMIN_MANAGER),
    ('sessions_list', 'get', lambda t: '/api/cashier-sessions/', no_data, BOUTIQUE_FIGURES),
    ('sessions_create', 'post', lambda t: '/api/cashier-sessions/', lambda t: {
        'shop': t.shop_a.id, 'cashier': t.target.id, 'period_type': 'daily',
        'start_date': (date.today() + timedelta(days=30)).isoformat(),
        'end_date': (date.today() + timedelta(days=30)).isoformat(),
    }, ADMIN_MANAGER),
    ('sessions_close', 'post', lambda t: f'/api/cashier-sessions/{t.session.id}/close/', no_data, ADMIN_MANAGER),
    ('sessions_delete_empty', 'delete', lambda t: f'/api/cashier-sessions/{t.past_empty_session.id}/',
     no_data, ADMIN_MANAGER),
    ('expenses_list', 'get', lambda t: '/api/expenses/', no_data, BOUTIQUE_FIGURES),
    ('expenses_create', 'post', lambda t: '/api/expenses/', lambda t: {
        'session': t.session.id, 'label': 'Transport', 'amount': '500',
        'sale_date': date.today().isoformat(),
    }, REGISTER),
    ('expenses_delete', 'delete', lambda t: f'/api/expenses/{t.expense.id}/', no_data, ADMIN_MANAGER),
]

# Cases qui planteraient (erreur 500). Vide depuis la correction des prix en masse (2026-11-09).
CRASHING_CELLS = set()


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


class FixedFlawTests(PermissionFixtures):
    """Anciens défauts connus, corrigés le 2026-11-09 : ces tests empêchent leur retour."""

    def test_bulk_update_prices_works(self):
        response = self.call(self.admin, 'post', '/api/products/bulk_update_prices/', {
            'product_ids': [self.product.id], 'percentage_increase': 10,
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.selling_price), '1100.00')

    def test_bulk_update_prices_refuses_absurd_percentages(self):
        for value in (-100, -150, 'abc', 'NaN'):
            response = self.call(self.admin, 'post', '/api/products/bulk_update_prices/', {
                'product_ids': [self.product.id], 'percentage_increase': value,
            })
            self.assertEqual(response.status_code, 400, value)

    def test_inventory_of_today_is_accepted_between_midnight_and_1am(self):
        """00 h 30 à Porto-Novo : la date locale est le 2, mais la comparaison se fait en UTC (le 1er)."""
        just_after_local_midnight = datetime(2026, 1, 1, 23, 30, tzinfo=dt_timezone.utc)
        with patch('apps.inventories.serializers.inventory.timezone.now', return_value=just_after_local_midnight):
            response = self.call(self.manager, 'post', '/api/inventories/', {
                'shop': self.shop_a.id, 'inventory_date': '2026-01-02',
            })
        self.assertEqual(response.status_code, 201, response.content)
