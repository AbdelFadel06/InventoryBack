"""Démo publique : données crédibles, remise à zéro, et mode démo qui protège les comptes partagés."""
import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.access.models import RolePermission
from apps.accounts.models import User
from apps.products.models import Product
from apps.sales.models import Sale, SaleIssue
from apps.shops.models import Shop
from apps.stocks.models import Stock

PASSWORD = 'Demo-ShopM-2026!'


def seed(*extra):
    with patch.dict(os.environ, {'ALLOW_DEMO_SEED': 'true'}):
        call_command('seed_demo', '--password', PASSWORD, *extra, stdout=StringIO())


class SeedDemoTests(TestCase):

    def test_refused_without_the_flag(self):
        with patch.dict(os.environ, {'ALLOW_DEMO_SEED': 'false'}):
            with self.assertRaises(CommandError):
                call_command('seed_demo', '--password', PASSWORD, stdout=StringIO())

    def test_creates_a_lively_shop(self):
        seed()
        shop = Shop.objects.get(name='Maison Akwaba')
        self.assertEqual(Product.objects.filter(shop=shop).count(), 34)
        self.assertGreater(Sale.objects.filter(shop=shop).count(), 200)
        self.assertTrue(Sale.objects.filter(shop=shop, created_at__date=timezone.localdate()).exists())
        self.assertTrue(Sale.objects.filter(sale_type='delivery').exists())
        # Stocks jamais négatifs, et des alertes à montrer.
        self.assertFalse(Stock.objects.filter(quantity__lt=0).exists())
        self.assertEqual(Stock.objects.filter(location='BOUTIQUE', quantity=0).count(), 2)
        self.assertEqual(SaleIssue.objects.filter(status='open').count(), 1)
        # Les comptes démo se connectent.
        client = APIClient()
        response = client.post('/api/token/', {'email': 'demo.manager@shopm.demo', 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_refuses_to_mix_with_existing_data_without_reset(self):
        Shop.objects.create(name='Vraie boutique')
        with self.assertRaises(CommandError):
            seed()



class SeedDemoResetTests(TransactionTestCase):
    """La remise à zéro vide la base (flush) : à tester hors transaction, comme en vrai."""

    # Le flush vide aussi les données posées par les migrations (grille des permissions) :
    # on les sauvegarde avant et on les restaure après, pour ne pas casser les tests suivants.
    serialized_rollback = True

    def test_reset_starts_again_and_keeps_the_permission_grid(self):
        seed()
        Sale.objects.all().delete()
        seed('--reset')
        self.assertEqual(Shop.objects.filter(name='Maison Akwaba').count(), 1)
        self.assertGreater(Sale.objects.count(), 200)
        self.assertTrue(RolePermission.objects.filter(role='SHOP_MANAGER', code='sales.cancel', allowed=True).exists())


@override_settings(DEMO_MODE=True)
class DemoModeTests(TestCase):

    def setUp(self):
        seed()
        self.client = APIClient()
        self.manager = User.objects.get(email='demo.manager@shopm.demo')
        self.client.force_authenticate(self.manager)

    def test_shared_accounts_cannot_be_changed(self):
        caisse = User.objects.get(email='demo.caisse@shopm.demo')
        for method, url in (('post', '/api/users/change_password/'), ('patch', '/api/users/update_profile/'),
                            ('patch', f'/api/users/{caisse.id}/'), ('delete', f'/api/users/{caisse.id}/'),
                            ('post', f'/api/users/{caisse.id}/toggle_active/')):
            response = getattr(self.client, method)(url, {}, format='json')
            self.assertEqual(response.status_code, 403, url)
            self.assertIn('démo', response.json()['error'])

    def test_everything_else_works(self):
        self.assertEqual(self.client.get('/api/products/').status_code, 200)
        self.assertEqual(self.client.get('/api/sales/').status_code, 200)

    @override_settings(DEMO_MODE=False)
    def test_off_outside_the_demo(self):
        response = self.client.post('/api/users/change_password/', {}, format='json')
        self.assertNotEqual(response.status_code, 403)
