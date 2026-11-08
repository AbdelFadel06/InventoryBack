"""Corrections du 2026-11-09 : stock vérifié en boutique, listes de comptes protégées, session modifiable."""
from datetime import timedelta

from django.utils import timezone

from apps.accounts.test_permissions_baseline import PermissionFixtures
from apps.stocks.models import Stock


class SaleChecksBoutiqueStockTests(PermissionFixtures):
    """La vente décrémente la boutique : c'est le stock de la boutique qu'il faut vérifier."""

    def sell(self, *quantities):
        return self.call(self.employee, 'post', '/api/sales/', {
            'items': [{'product': self.product.id, 'quantity': q} for q in quantities],
        })

    def set_stock(self, boutique, magasin):
        Stock.objects.filter(id=self.boutique_stock.id).update(quantity=boutique)
        Stock.objects.filter(id=self.stock.id).update(quantity=magasin)

    def test_full_warehouse_does_not_hide_an_empty_boutique(self):
        self.set_stock(boutique=0, magasin=10)
        response = self.sell(1)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('boutique', str(response.json()))

    def test_empty_warehouse_does_not_block_a_stocked_boutique(self):
        self.set_stock(boutique=5, magasin=0)
        self.assertEqual(self.sell(2).status_code, 201)

    def test_same_product_on_two_lines_is_checked_on_the_total(self):
        self.set_stock(boutique=3, magasin=0)
        self.assertEqual(self.sell(2, 2).status_code, 400)
        self.assertEqual(Stock.objects.get(id=self.boutique_stock.id).quantity, 3)


class UserListActionsTests(PermissionFixtures):
    """Les listes d'aide aux écrans respectent enfin leurs permissions déclarées."""

    def test_managers_list_is_for_the_super_admin(self):
        self.assertEqual(self.call(self.admin, 'get', '/api/users/managers/').status_code, 200)
        for user in (self.manager, self.employee, self.magasinier, self.livreur):
            self.assertEqual(self.call(user, 'get', '/api/users/managers/').status_code, 403, user.email)

    def test_employees_list_is_for_managers_and_admin(self):
        for user in (self.admin, self.manager):
            self.assertEqual(self.call(user, 'get', '/api/users/employees/').status_code, 200, user.email)
        for user in (self.employee, self.magasinier, self.livreur):
            self.assertEqual(self.call(user, 'get', '/api/users/employees/').status_code, 403, user.email)

    def test_own_account_routes_stay_open(self):
        for user in (self.employee, self.livreur, self.magasinier):
            self.assertEqual(self.call(user, 'get', '/api/users/me/').status_code, 200, user.email)
            self.assertEqual(self.call(user, 'get', '/api/users/livreurs/').status_code, 200, user.email)


class CashierSessionPartialUpdateTests(PermissionFixtures):

    def url(self):
        return f'/api/cashier-sessions/{self.session.id}/'

    def test_empty_patch_no_longer_crashes(self):
        self.assertEqual(self.call(self.manager, 'patch', self.url(), {}).status_code, 200)

    def test_patch_only_notes_keeps_the_dates(self):
        response = self.call(self.manager, 'patch', self.url(), {'notes': 'Relève à 14 h'})
        self.assertEqual(response.status_code, 200, response.content)
        self.session.refresh_from_db()
        self.assertEqual(self.session.notes, 'Relève à 14 h')
        self.assertEqual(self.session.start_date, timezone.localdate())

    def test_patch_end_before_start_is_refused(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.call(self.manager, 'patch', self.url(), {'end_date': yesterday})
        self.assertEqual(response.status_code, 400)
