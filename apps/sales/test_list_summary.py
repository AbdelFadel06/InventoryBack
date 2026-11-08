"""Listes paginées : filtres côté serveur et totaux calculés sur toute la liste, pas sur la page."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.test_permissions_baseline import PermissionFixtures
from apps.products.models import Product
from apps.sales.models import CashierSession, Sale
from apps.stocks.models import Stock

LISTS = ['/api/stocks/', '/api/stock-movements/', '/api/stock-transfers/', '/api/inventories/',
         '/api/users/', '/api/cashier-sessions/', '/api/sales/']


class SummaryRightsTests(PermissionFixtures):

    def test_summary_has_exactly_the_rights_of_the_list(self):
        for url in LISTS:
            for user in (self.admin, self.manager, self.employee, self.livreur, self.magasinier):
                listed = self.call(user, 'get', url).status_code
                summed = self.call(user, 'get', f'{url}counts/').status_code
                self.assertEqual(summed, listed, f'{url} {user.email}')

    def test_summary_stays_in_the_active_shop(self):
        Sale.objects.create(shop=self.shop_b, cashier=self.employee_b, session=CashierSession.objects.create(
            shop=self.shop_b, cashier=self.employee_b, created_by=self.manager_b,
            start_date=timezone.localdate(), end_date=timezone.localdate(),
        ), total_amount=999)
        body = self.call(self.manager, 'get', '/api/sales/counts/').json()
        self.assertEqual(body['total'], Sale.objects.filter(shop=self.shop_a, created_at__date=timezone.localdate()).count())


class StockFilterTests(PermissionFixtures):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # 25 produits en rupture, 3 en stock correct : plus de deux pages de ruptures.
        for i in range(28):
            product = Product.objects.create(
                name=f'P{i:02}', sku=f'SKU-{i}', category=cls.category, selling_price=100,
                shop=cls.shop_a, minimum_stock=5, reorder_level=10,
            )
            Stock.objects.create(product=product, shop=cls.shop_a, location='BOUTIQUE', quantity=0 if i < 25 else 50)

    def test_every_page_of_a_status_filter_is_full(self):
        first = self.call(self.manager, 'get', '/api/stocks/', {'stock_status': 'out_of_stock'}).json()
        second = self.call(self.manager, 'get', '/api/stocks/', {'stock_status': 'out_of_stock', 'page': 2}).json()
        self.assertEqual(first['count'], 25)
        self.assertEqual(len(first['results']), 10)
        self.assertEqual(len(second['results']), 10)
        self.assertTrue(all(s['stock_status'] == 'out_of_stock' for s in first['results'] + second['results']))

    def test_status_rules_match_the_model(self):
        for name in ('out_of_stock', 'critical', 'low', 'ok'):
            rows = self.call(self.manager, 'get', '/api/stocks/', {'stock_status': name, 'page_size': 500}).json()['results']
            expected = [s for s in Stock.objects.filter(shop=self.shop_a) if s.stock_status == name]
            self.assertEqual(len(rows), len(expected), name)

    def test_summary_counts_the_whole_list_and_follows_the_search(self):
        body = self.call(self.manager, 'get', '/api/stocks/counts/', {'location': 'BOUTIQUE'}).json()
        self.assertEqual(body['by']['out_of_stock'], 25)
        self.assertEqual(body['total'], Stock.objects.filter(shop=self.shop_a, location='BOUTIQUE').count())
        searched = self.call(self.manager, 'get', '/api/stocks/counts/', {'search': 'P0'}).json()
        self.assertEqual(searched['total'], 10)


class SalesAndSessionsSummaryTests(PermissionFixtures):

    def test_sales_summary_adds_up_every_sale_of_the_day(self):
        Sale.objects.filter(id=self.sale.id).update(created_at=timezone.now() - timedelta(days=2))
        for i in range(12):
            Sale.objects.create(shop=self.shop_a, cashier=self.employee, session=self.session, total_amount=1000,
                                payment_status='pending' if i == 0 else 'paid')
        Sale.objects.create(shop=self.shop_a, cashier=self.employee, session=self.session, total_amount=500, status='cancelled')
        body = self.call(self.manager, 'get', '/api/sales/counts/').json()
        self.assertEqual(body['completed'], 12)
        self.assertEqual(body['cancelled'], 1)
        self.assertEqual(body['unpaid'], 1)
        self.assertEqual(Decimal(str(body['revenue'])), Decimal('12000'))

    def test_session_states(self):
        today = timezone.localdate()
        CashierSession.objects.create(shop=self.shop_a, cashier=self.target, created_by=self.manager,
                                      start_date=today + timedelta(days=2), end_date=today + timedelta(days=2))
        body = self.call(self.manager, 'get', '/api/cashier-sessions/counts/').json()
        self.assertEqual(body['by'], {'current': 1, 'upcoming': 1, 'closed': 1})
        upcoming = self.call(self.manager, 'get', '/api/cashier-sessions/', {'state': 'upcoming'}).json()
        self.assertEqual(upcoming['count'], 1)
