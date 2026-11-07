"""Le caissier signale un problème sur une vente, le manager le traite au point du soir."""
from datetime import date

from apps.accounts.test_permissions_baseline import PermissionFixtures
from apps.sales.models import CashierSession, Sale, SaleIssue
from apps.shops.models import Shop


class ReportIssueTests(PermissionFixtures):

    def report(self, user, body=None):
        return self.call(user, 'post', f'/api/sales/{self.sale.id}/report_issue/', body or {'reason': 'wrong_amount'})

    def test_cashier_reports_and_the_sale_does_not_change(self):
        before = Sale.objects.values('status', 'payment_status', 'total_amount').get(id=self.sale.id)
        stock_before = self.boutique_stock.quantity

        response = self.report(self.employee, {'reason': 'wrong_item', 'comment': 'Mauvaise couleur'})

        self.assertEqual(response.status_code, 201, response.content)
        issue = SaleIssue.objects.get(sale=self.sale)
        self.assertEqual(issue.status, 'open')
        self.assertEqual(issue.reported_by, self.employee)
        self.assertEqual(Sale.objects.values('status', 'payment_status', 'total_amount').get(id=self.sale.id), before)
        self.boutique_stock.refresh_from_db()
        self.assertEqual(self.boutique_stock.quantity, stock_before)

    def test_only_cashier_and_manager_can_report(self):
        self.assertEqual(self.report(self.manager).status_code, 201)
        SaleIssue.objects.all().delete()
        for user in (self.target, self.magasinier, self.livreur, self.admin):
            self.assertEqual(self.report(user).status_code, 403, user.email)
        self.assertFalse(SaleIssue.objects.exists())

    def test_other_reason_requires_a_comment(self):
        response = self.report(self.employee, {'reason': 'other', 'comment': '  '})
        self.assertEqual(response.status_code, 400)
        self.assertIn('comment', response.json())

    def test_unknown_reason_is_refused(self):
        self.assertEqual(self.report(self.employee, {'reason': 'nimporte'}).status_code, 400)

    def test_a_sale_cannot_have_two_open_issues(self):
        self.report(self.employee)
        self.assertEqual(self.report(self.employee).status_code, 400)

    def test_a_resolved_sale_can_be_reported_again(self):
        self.report(self.employee)
        SaleIssue.objects.update(status='resolved')
        self.assertEqual(self.report(self.employee).status_code, 201)

    def test_a_cancelled_sale_cannot_be_reported(self):
        Sale.objects.filter(id=self.sale.id).update(status='cancelled')
        self.assertEqual(self.report(self.employee).status_code, 400)

    def test_sale_detail_shows_the_open_issue(self):
        self.report(self.employee, {'reason': 'client_return', 'comment': 'Retour'})
        response = self.call(self.employee, 'get', f'/api/sales/{self.sale.id}/')
        self.assertEqual(response.json()['open_issue']['reason_label'], 'Client revenu')


class ResolveIssueTests(PermissionFixtures):

    def setUp(self):
        super().setUp()
        self.issue = SaleIssue.objects.create(sale=self.sale, reason='wrong_amount', reported_by=self.employee)

    def resolve(self, user, note='Corrigé'):
        return self.call(user, 'post', f'/api/sale-issues/{self.issue.id}/resolve/', {'note': note})

    def test_manager_resolves_with_a_note(self):
        response = self.resolve(self.manager, ' Montant corrigé ')
        self.assertEqual(response.status_code, 200, response.content)
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, 'resolved')
        self.assertEqual(self.issue.resolved_by, self.manager)
        self.assertEqual(self.issue.resolution_note, 'Montant corrigé')
        self.assertIsNotNone(self.issue.resolved_at)

    def test_note_is_required(self):
        self.assertEqual(self.resolve(self.manager, '  ').status_code, 400)

    def test_cannot_resolve_twice(self):
        self.resolve(self.manager)
        self.assertEqual(self.resolve(self.manager).status_code, 400)

    def test_only_managers_read_and_resolve(self):
        for user in (self.employee, self.target, self.magasinier, self.livreur):
            self.assertEqual(self.call(user, 'get', '/api/sale-issues/').status_code, 403, user.email)
            self.assertEqual(self.resolve(user).status_code, 403, user.email)

    def test_open_issues_can_be_counted_for_the_dashboard(self):
        response = self.call(self.manager, 'get', '/api/sale-issues/?status=open')
        self.assertEqual(response.json()['count'], 1)
        response = self.call(self.manager, 'get', '/api/sale-issues/?status=resolved')
        self.assertEqual(response.json()['count'], 0)

    def test_manager_of_another_shop_cannot_see_or_resolve(self):
        self.assertEqual(self.call(self.manager_b, 'get', '/api/sale-issues/').json()['count'], 0)
        self.assertEqual(self.resolve(self.manager_b).status_code, 404)

    def test_cancelling_the_sale_closes_its_open_issue(self):
        response = self.call(self.manager, 'post', f'/api/sales/{self.sale.id}/cancel/', {'reason': 'Client revenu'})
        self.assertEqual(response.status_code, 200, response.content)
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, 'resolved')
        self.assertEqual(self.issue.resolved_by, self.manager)
        self.assertIn('Client revenu', self.issue.resolution_note)


class AllShopsIssuesTests(PermissionFixtures):
    """La cloche du manager liste les signalements de toutes ses boutiques, quelle que soit l'active."""

    def setUp(self):
        super().setUp()
        self.shop_c = Shop.objects.create(name='Boutique C')
        self.shop_c.managers.add(self.manager)
        session_c = CashierSession.objects.create(
            shop=self.shop_c, cashier=self.manager, created_by=self.manager,
            start_date=date.today(), end_date=date.today(),
        )
        sale_c = Sale.objects.create(
            shop=self.shop_c, cashier=self.manager, session=session_c, total_amount=500,
            payment_method='cash', payment_status='paid',
        )
        session_b = CashierSession.objects.create(
            shop=self.shop_b, cashier=self.employee_b, created_by=self.manager_b,
            start_date=date.today(), end_date=date.today(),
        )
        sale_b = Sale.objects.create(
            shop=self.shop_b, cashier=self.employee_b, session=session_b, total_amount=700,
            payment_method='cash', payment_status='paid',
        )
        self.issue_a = SaleIssue.objects.create(sale=self.sale, reason='wrong_amount', reported_by=self.employee)
        self.issue_c = SaleIssue.objects.create(sale=sale_c, reason='wrong_item', reported_by=self.manager)
        self.issue_b = SaleIssue.objects.create(sale=sale_b, reason='other', reported_by=self.employee_b)

    def ids(self, user, query, **headers):
        response = self.call(user, 'get', f'/api/sale-issues/{query}', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return {row['id'] for row in response.json()['results']}

    def test_scope_all_covers_every_managed_shop_and_only_them(self):
        self.assertEqual(self.ids(self.manager, '?status=open&scope=all'), {self.issue_a.id, self.issue_c.id})

    def test_without_scope_the_active_shop_still_applies(self):
        self.assertEqual(self.ids(self.manager, '?status=open'), {self.issue_a.id})
        self.assertEqual(
            self.ids(self.manager, '?status=open', HTTP_X_ACTIVE_SHOP=str(self.shop_c.id)), {self.issue_c.id},
        )

    def test_rows_name_their_shop(self):
        response = self.call(self.manager, 'get', '/api/sale-issues/?scope=all')
        shops = {row['id']: (row['shop'], row['shop_name']) for row in response.json()['results']}
        self.assertEqual(shops[self.issue_c.id], (self.shop_c.id, 'Boutique C'))

    def test_other_roles_are_still_refused(self):
        for user in (self.employee, self.magasinier, self.livreur):
            self.assertEqual(self.call(user, 'get', '/api/sale-issues/?scope=all').status_code, 403, user.email)
