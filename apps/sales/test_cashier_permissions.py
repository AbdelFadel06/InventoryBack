"""
Règles validées pour la caisse : vente, dépense et argent d'un livreur sont réservés
au manager et au caissier de la session active. Une vente n'est jamais supprimée.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from apps.accounts.test_permissions_baseline import PermissionFixtures, make_user
from apps.sales.models import CashierSession, Expense, Sale
from apps.stocks.models import Stock, StockMovement


def sale_body(product):
    return {'items': [{'product': product.id, 'quantity': 1}]}


def expense_body(session):
    return {'session': session.id, 'label': 'Transport', 'amount': '500', 'sale_date': date.today().isoformat()}


class ActiveCashierTests(PermissionFixtures):
    """`employee` est le caissier du jour, `target` un employé de la même boutique."""

    def test_other_employee_cannot_use_the_register(self):
        attempts = {
            'vente': self.call(self.target, 'post', '/api/sales/', sale_body(self.product)),
            'dépense': self.call(self.target, 'post', '/api/expenses/', expense_body(self.session)),
            'paiement': self.call(self.target, 'post', f'/api/sales/{self.sale.id}/validate_payment/'),
            'modification': self.call(self.target, 'post', f'/api/sales/{self.sale.id}/modify_items/', {
                'items': [{'product_id': self.product.id, 'quantity': 1}],
            }),
        }
        for name, response in attempts.items():
            self.assertEqual(response.status_code, 403, f'{name} : {response.content}')

    def test_cashier_loses_access_when_the_session_is_over(self):
        CashierSession.objects.filter(id=self.session.id).update(status='closed')
        response = self.call(self.employee, 'post', '/api/sales/', sale_body(self.product))
        self.assertEqual(response.status_code, 403)

    def test_cashier_loses_access_when_the_session_has_expired(self):
        yesterday = date.today() - timedelta(days=1)
        CashierSession.objects.filter(id=self.session.id).update(start_date=yesterday, end_date=yesterday)
        response = self.call(self.employee, 'post', '/api/expenses/', expense_body(self.session))
        self.assertEqual(response.status_code, 403)

    def test_cashier_validates_a_payment_from_a_previous_session(self):
        """Un livreur peut rapporter l'argent le lendemain, à un autre caissier."""
        old_sale = Sale.objects.create(
            shop=self.shop_a, cashier=self.target, session=self.past_empty_session,
            sale_type='delivery', livreur=self.livreur, total_amount=500,
            payment_method='on_delivery', payment_status='pending',
        )
        response = self.call(self.employee, 'post', f'/api/sales/{old_sale.id}/validate_payment/')
        self.assertEqual(response.status_code, 200, response.content)

    def test_cashier_cannot_attach_an_expense_to_an_old_session(self):
        response = self.call(self.employee, 'post', '/api/expenses/', expense_body(self.past_empty_session))
        self.assertEqual(response.status_code, 400)
        self.assertIn('session', response.json())

    def test_manager_cannot_attach_an_expense_to_another_shop(self):
        session_b = CashierSession.objects.create(
            shop=self.shop_b, cashier=self.employee_b, created_by=self.manager_b,
            start_date=date.today(), end_date=date.today(),
        )
        response = self.call(self.manager, 'post', '/api/expenses/', expense_body(session_b))
        self.assertEqual(response.status_code, 400)

    def test_session_of_the_new_day_is_found_just_after_local_midnight(self):
        """00 h 30 à Porto-Novo correspond à 23 h 30 UTC la veille."""
        CashierSession.objects.filter(id=self.session.id).update(
            start_date=date(2026, 1, 2), end_date=date(2026, 1, 2),
        )
        just_after_local_midnight = datetime(2026, 1, 1, 23, 30, tzinfo=dt_timezone.utc)
        with patch('django.utils.timezone.now', return_value=just_after_local_midnight):
            self.assertEqual(CashierSession.active_for_shop(self.shop_a), self.session)


class DeliveryModificationTests(PermissionFixtures):

    def modify(self, user):
        return self.call(user, 'post', f'/api/sales/{self.sale.id}/modify_items/', {
            'items': [{'product_id': self.product.id, 'quantity': 1}],
        })

    def test_cashier_modifies_a_delivery_not_yet_collected(self):
        self.assertEqual(self.modify(self.employee).status_code, 200)

    def test_cashier_cannot_modify_a_collected_delivery(self):
        Sale.objects.filter(id=self.sale.id).update(delivered_at=datetime.now(dt_timezone.utc))
        self.assertEqual(self.modify(self.employee).status_code, 403)

    def test_cashier_cannot_modify_a_paid_delivery(self):
        Sale.objects.filter(id=self.sale.id).update(payment_status='paid')
        self.assertEqual(self.modify(self.employee).status_code, 403)

    def test_manager_can_correct_a_collected_delivery(self):
        Sale.objects.filter(id=self.sale.id).update(delivered_at=datetime.now(dt_timezone.utc))
        self.assertEqual(self.modify(self.manager).status_code, 200)


class SaleCancellationTests(PermissionFixtures):

    def test_cancellation_requires_a_reason(self):
        for body in (None, {'reason': ''}, {'reason': '   '}):
            response = self.call(self.manager, 'post', f'/api/sales/{self.sale.id}/cancel/', body)
            self.assertEqual(response.status_code, 400, body)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, 'completed')

    def test_cancellation_keeps_a_trace_and_restocks(self):
        Sale.objects.filter(id=self.sale.id).update(sale_type='direct')
        response = self.call(self.manager, 'post', f'/api/sales/{self.sale.id}/cancel/', {'reason': ' Client revenu '})
        self.assertEqual(response.status_code, 200, response.content)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, 'cancelled')
        self.assertEqual(self.sale.cancel_reason, 'Client revenu')
        self.assertEqual(self.sale.cancelled_by, self.manager)
        self.assertIsNotNone(self.sale.cancelled_at)
        self.assertEqual(response.json()['cancel_reason'], 'Client revenu')

    def test_cashier_cannot_cancel(self):
        response = self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/cancel/', {'reason': 'x'})
        self.assertEqual(response.status_code, 403)

    def test_sales_cannot_be_deleted_by_anyone(self):
        for user in (self.admin, self.manager, self.employee):
            response = self.call(user, 'delete', f'/api/sales/{self.sale.id}/')
            self.assertIn(response.status_code, (403, 405))
        self.assertTrue(Sale.objects.filter(id=self.sale.id).exists())


class SessionDeletionTests(PermissionFixtures):

    def test_session_with_sales_cannot_be_deleted(self):
        for user in (self.admin, self.manager):
            response = self.call(user, 'delete', f'/api/cashier-sessions/{self.session.id}/')
            self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(Sale.objects.filter(id=self.sale.id).exists())

    def test_session_with_only_expenses_cannot_be_deleted(self):
        Sale.objects.filter(id=self.sale.id).delete()
        response = self.call(self.manager, 'delete', f'/api/cashier-sessions/{self.session.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Expense.objects.filter(id=self.expense.id).exists())

    def test_magasinier_cannot_delete_a_session(self):
        response = self.call(self.magasinier, 'delete', f'/api/cashier-sessions/{self.past_empty_session.id}/')
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_open_a_session_in_another_shop(self):
        response = self.call(self.manager, 'post', '/api/cashier-sessions/', {
            'shop': self.shop_b.id, 'cashier': self.employee_b.id, 'period_type': 'daily',
            'start_date': date.today().isoformat(), 'end_date': date.today().isoformat(),
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('shop', response.json())


class LivreurTests(PermissionFixtures):

    def setUp(self):
        super().setUp()
        self.other_livreur = make_user('livreur2@test.local', 'LIVREUR', self.shop_a)

    def test_livreur_cannot_confirm_the_delivery_of_another(self):
        response = self.call(self.other_livreur, 'post', f'/api/sales/{self.sale.id}/mark_delivered/')
        self.assertEqual(response.status_code, 404)

    def test_livreur_cannot_read_the_deliveries_of_another(self):
        url = f'/api/sales/livreur_point/?livreur_id={self.livreur.id}&date={self.sale.created_at.date()}'
        response = self.call(self.other_livreur, 'get', url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_count'], 0)

    def test_livreur_cannot_validate_their_own_payment(self):
        response = self.call(self.livreur, 'post', f'/api/sales/{self.sale.id}/validate_payment/')
        self.assertEqual(response.status_code, 403)


class StockRulesTests(PermissionFixtures):

    def test_employee_cannot_add_stock(self):
        response = self.call(self.employee, 'post', '/api/stock-movements/add_stock/', {
            'product': self.product.id, 'shop': self.shop_a.id, 'location': 'MAGASIN', 'quantity': 5,
        })
        self.assertEqual(response.status_code, 403)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 10)

    def test_magasinier_cannot_touch_boutique_stock(self):
        for action in ('add_stock', 'remove_stock'):
            response = self.call(self.magasinier, 'post', f'/api/stock-movements/{action}/', {
                'product': self.product.id, 'shop': self.shop_a.id, 'location': 'BOUTIQUE', 'quantity': 1,
            })
            self.assertEqual(response.status_code, 403, action)
        self.boutique_stock.refresh_from_db()
        self.assertEqual(self.boutique_stock.quantity, 10)

    def test_a_sale_still_moves_the_stock_for_the_cashier(self):
        """Interdire les routes de stock à l'employé ne doit pas bloquer ses ventes."""
        response = self.call(self.employee, 'post', '/api/sales/', sale_body(self.product))
        self.assertEqual(response.status_code, 201, response.content)
        self.boutique_stock.refresh_from_db()
        self.assertEqual(self.boutique_stock.quantity, 9)
        self.assertTrue(StockMovement.objects.filter(movement_type='exit', created_by=self.employee).exists())

    def test_multi_shop_manager_reads_stock_of_their_active_shop(self):
        self.shop_b.managers.add(self.manager)
        stock_b = Stock.objects.create(product=self.product, shop=self.shop_b, location='MAGASIN', quantity=3)
        response = self.call(
            self.manager, 'get', f'/api/stocks/{stock_b.id}/',
            HTTP_X_ACTIVE_SHOP=str(self.shop_b.id),
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_manager_cannot_read_stock_of_a_shop_they_do_not_manage(self):
        stock_b = Stock.objects.create(product=self.product, shop=self.shop_b, location='MAGASIN', quantity=3)
        response = self.call(
            self.manager, 'get', f'/api/stocks/{stock_b.id}/',
            HTTP_X_ACTIVE_SHOP=str(self.shop_b.id),
        )
        self.assertEqual(response.status_code, 404)
