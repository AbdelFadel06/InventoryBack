"""Le manager corrige une vente : l'ancienne est annulée et la juste la remplace, en une seule opération."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.accounts.test_permissions_baseline import PermissionFixtures
from apps.sales.models import Sale, SaleIssue
from apps.stocks.models import Stock


class SaleCorrectionTests(PermissionFixtures):

    def setUp(self):
        super().setUp()
        response = self.call(self.employee, 'post', '/api/sales/', {
            'sale_type': 'direct', 'payment_method': 'cash',
            'items': [{'product': self.product.id, 'quantity': 3}],
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.original = Sale.objects.get(id=response.json()['id'])

    def stock_total(self):
        return Stock.objects.filter(product=self.product).aggregate(total=Sum('quantity'))['total']

    def correct(self, user, items, reason='Mauvaise quantité', **fields):
        body = {'reason': reason, 'sale_type': 'direct', 'payment_method': 'cash', 'items': items, **fields}
        return self.call(user, 'post', f'/api/sales/{self.original.id}/correct/', body)

    def test_manager_replaces_the_sale_and_stock_follows(self):
        stock_before = self.stock_total()
        response = self.correct(self.manager, [{'product': self.product.id, 'quantity': 2}])
        self.assertEqual(response.status_code, 201, response.content)

        self.original.refresh_from_db()
        self.assertEqual(self.original.status, 'cancelled')
        self.assertEqual(self.original.cancelled_by, self.manager)
        self.assertEqual(self.original.cancel_reason, 'Corrigée : Mauvaise quantité')

        corrected = Sale.objects.get(id=response.json()['id'])
        self.assertEqual(corrected.corrected_from, self.original)
        self.assertEqual(corrected.total_amount, Decimal('2000'))
        # Reste au nom du caissier, dans la même session et à la même date.
        self.assertEqual(corrected.cashier, self.employee)
        self.assertEqual(corrected.session, self.original.session)
        self.assertEqual(corrected.created_at, self.original.created_at)
        # 3 rendus, 2 repris.
        self.assertEqual(self.stock_total(), stock_before + 1)

    def test_both_sales_point_to_each_other(self):
        corrected_id = self.correct(self.manager, [{'product': self.product.id, 'quantity': 2}]).json()['id']
        original = self.call(self.manager, 'get', f'/api/sales/{self.original.id}/').json()
        corrected = self.call(self.manager, 'get', f'/api/sales/{corrected_id}/').json()
        self.assertEqual(original['corrected_by_sale']['id'], corrected_id)
        self.assertEqual(corrected['corrected_from_reference'], self.original.reference)

    def test_original_price_can_be_kept(self):
        response = self.correct(self.manager, [{'product': self.product.id, 'quantity': 3, 'unit_price': '800'}])
        self.assertEqual(Decimal(response.json()['total_amount']), Decimal('2400'))

    def test_the_register_cannot_set_its_own_price(self):
        response = self.call(self.employee, 'post', '/api/sales/', {
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '1'}],
        })
        self.assertEqual(Decimal(response.json()['total_amount']), Decimal('1000'))

    def test_refused_correction_changes_nothing(self):
        stock_before = self.stock_total()
        response = self.correct(self.manager, [{'product': self.product.id, 'quantity': 500}])
        self.assertEqual(response.status_code, 400)
        self.original.refresh_from_db()
        self.assertEqual(self.original.status, 'completed')
        self.assertEqual(self.stock_total(), stock_before)
        self.assertEqual(Sale.objects.filter(corrected_from=self.original).count(), 0)

    def test_closes_the_open_issue(self):
        issue = SaleIssue.objects.create(sale=self.original, reason='wrong_amount', reported_by=self.employee)
        self.correct(self.manager, [{'product': self.product.id, 'quantity': 2}])
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'resolved')
        self.assertIn('Mauvaise quantité', issue.resolution_note)

    def test_reason_is_required_and_a_sale_is_corrected_once(self):
        self.assertEqual(self.correct(self.manager, [{'product': self.product.id, 'quantity': 2}], reason=' ').status_code, 400)
        self.assertEqual(self.correct(self.manager, [{'product': self.product.id, 'quantity': 2}]).status_code, 201)
        self.assertEqual(self.correct(self.manager, [{'product': self.product.id, 'quantity': 1}]).status_code, 400)

    def test_only_managers_correct(self):
        for user in (self.employee, self.target, self.magasinier, self.livreur):
            response = self.correct(user, [{'product': self.product.id, 'quantity': 2}])
            self.assertEqual(response.status_code, 403, user.email)
        self.assertEqual(self.correct(self.manager_b, [{'product': self.product.id, 'quantity': 2}]).status_code, 404)

    def test_works_on_a_past_day_without_an_open_session(self):
        past = timezone.now() - timedelta(days=3)
        Sale.objects.filter(id=self.original.id).update(created_at=past)
        # Plus aucune session du jour : la correction reprend celle de la vente d'origine.
        self.session.__class__.objects.filter(id=self.session.id).update(
            start_date=past.date(), end_date=past.date(),
        )
        response = self.correct(self.manager, [{'product': self.product.id, 'quantity': 2}])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Sale.objects.get(id=response.json()['id']).created_at, past)

    def test_paid_delivery_stays_paid(self):
        Sale.objects.filter(id=self.original.id).update(
            sale_type='delivery', livreur=self.livreur, payment_method='on_delivery',
            payment_status='paid', delivered_at=timezone.now(), livreur_paid=True,
        )
        response = self.correct(
            self.manager, [{'product': self.product.id, 'quantity': 2}],
            sale_type='delivery', payment_method='on_delivery', livreur=self.livreur.id,
        )
        self.assertEqual(response.status_code, 201, response.content)
        corrected = Sale.objects.get(id=response.json()['id'])
        self.assertEqual(corrected.payment_status, 'paid')
        self.assertTrue(corrected.livreur_paid)
        self.assertIsNotNone(corrected.delivered_at)
