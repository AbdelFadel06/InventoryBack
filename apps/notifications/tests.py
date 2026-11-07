"""Notifications téléphone : seuls les managers de la boutique concernée les reçoivent."""
import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from py_vapid import Vapid

from apps.accounts.test_permissions_baseline import PermissionFixtures, make_user
from apps.notifications.models import PushSubscription
from apps.sales.models import Sale
from apps.stocks.models import Stock, StockMovement

KEYS = {'VAPID_PUBLIC_KEY': 'public', 'VAPID_PRIVATE_KEY': 'private'}


def subscription(n):
    return {'endpoint': f'https://push.example.com/{n}', 'keys': {'p256dh': 'p' * 10, 'auth': 'a' * 10}}


def run_now(function, *args):
    function(*args)


@override_settings(**KEYS)
@patch('apps.notifications.push.run_in_background', run_now)
@patch('pywebpush.webpush')
class PushTests(PermissionFixtures):

    def subscribe(self, user, n):
        return self.call(user, 'post', '/api/notifications/push/subscribe/', subscription(n))

    def sent(self, webpush):
        return {c.kwargs['subscription_info']['endpoint']: json.loads(c.kwargs['data']) for c in webpush.call_args_list}

    def test_only_managers_subscribe(self, webpush):
        self.assertEqual(self.subscribe(self.manager, 1).status_code, 201)
        for user in (self.admin, self.employee, self.magasinier, self.livreur):
            self.assertEqual(self.subscribe(user, 2).status_code, 403, user.email)
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_resubscribing_the_same_phone_does_not_duplicate(self, webpush):
        self.subscribe(self.manager, 1)
        self.subscribe(self.manager, 1)
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_reported_sale_reaches_the_shop_managers_only(self, webpush):
        self.subscribe(self.manager, 'a')
        self.subscribe(self.manager_b, 'b')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/report_issue/', {'reason': 'wrong_amount'})
        self.assertEqual(response.status_code, 201, response.content)

        sent = self.sent(webpush)
        self.assertEqual(list(sent), ['https://push.example.com/a'])
        self.assertIn('Vente signalée', sent['https://push.example.com/a']['title'])
        self.assertIn('Erreur de montant', sent['https://push.example.com/a']['body'])
        self.assertEqual(sent['https://push.example.com/a']['url'], f'/manager/signalements?sale={self.sale.id}&shop={self.shop_a.id}')

    def test_manager_away_from_the_shop_is_still_notified(self, webpush):
        # Le manager est rattaché à la boutique B mais gère aussi la A.
        away = make_user('away@test.local', 'SHOP_MANAGER', self.shop_b)
        self.shop_a.managers.add(away)
        self.subscribe(away, 'away')
        with self.captureOnCommitCallbacks(execute=True):
            self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/report_issue/', {'reason': 'wrong_item'})
        self.assertIn('https://push.example.com/away', self.sent(webpush))

    def test_last_unit_sold_announces_the_stock_out(self, webpush):
        self.subscribe(self.manager, 'a')
        Stock.objects.filter(id=self.boutique_stock.id).update(quantity=2)
        with self.captureOnCommitCallbacks(execute=True):
            self.call(self.employee, 'post', '/api/sales/', {'items': [{'product': self.product.id, 'quantity': 1}]})
        self.assertEqual(webpush.call_count, 0)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call(self.employee, 'post', '/api/sales/', {'items': [{'product': self.product.id, 'quantity': 1}]})
        self.assertEqual(response.status_code, 201, response.content)

        message = self.sent(webpush)['https://push.example.com/a']
        self.assertIn('Rupture de stock', message['title'])
        self.assertIn('Produit A', message['body'])

    def test_empty_warehouse_does_not_ring(self, webpush):
        self.subscribe(self.manager, 'a')
        with self.captureOnCommitCallbacks(execute=True):
            StockMovement.objects.create(
                product=self.product, shop=self.shop_a, location='MAGASIN',
                movement_type='adjustment', quantity=-10, created_by=self.manager,
            )
        self.assertEqual(webpush.call_count, 0)

    def test_sending_failure_never_breaks_the_sale(self, webpush):
        webpush.side_effect = RuntimeError('service injoignable')
        self.subscribe(self.manager, 'a')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/report_issue/', {'reason': 'wrong_item'})
        self.assertEqual(response.status_code, 201)

    def test_dead_phone_is_forgotten(self, webpush):
        from pywebpush import WebPushException

        class Gone:
            status_code = 410
        webpush.side_effect = WebPushException('gone', response=Gone())
        self.subscribe(self.manager, 'a')
        with self.captureOnCommitCallbacks(execute=True):
            self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/report_issue/', {'reason': 'wrong_item'})
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_unsubscribe_and_key(self, webpush):
        self.subscribe(self.manager, 'a')
        key = self.call(self.manager, 'get', '/api/notifications/push/key/').json()
        self.assertEqual(key, {'public_key': 'public', 'allowed': True})
        self.assertFalse(self.call(self.admin, 'get', '/api/notifications/push/key/').json()['allowed'])
        self.call(self.manager, 'post', '/api/notifications/push/unsubscribe/', {'endpoint': 'https://push.example.com/a'})
        self.assertEqual(PushSubscription.objects.count(), 0)


@override_settings(VAPID_PUBLIC_KEY='', VAPID_PRIVATE_KEY='')
class WithoutKeysTests(PermissionFixtures):

    @patch('pywebpush.webpush')
    def test_nothing_is_sent_without_keys(self, webpush):
        PushSubscription.objects.create(user=self.manager, endpoint='https://push.example.com/a', p256dh='p', auth='a')
        with self.captureOnCommitCallbacks(execute=True):
            self.call(self.employee, 'post', f'/api/sales/{self.sale.id}/report_issue/', {'reason': 'wrong_item'})
        webpush.assert_not_called()
        self.assertEqual(self.call(self.manager, 'get', '/api/notifications/push/key/').json()['public_key'], '')

    def test_generated_keys_are_usable(self):
        out = StringIO()
        call_command('generate_vapid_keys', stdout=out)
        lines = dict(line.split('=', 1) for line in out.getvalue().split())
        signer = Vapid.from_string(lines['VAPID_PRIVATE_KEY'])
        self.assertTrue(signer.sign({'sub': 'https://shopm.test', 'aud': 'https://push.example.com'}))

    @override_settings(**KEYS)
    def test_existing_keys_are_never_replaced(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('generate_vapid_keys', stdout=StringIO())
