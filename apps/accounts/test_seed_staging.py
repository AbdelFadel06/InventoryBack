import os
from unittest.mock import patch

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.products.models import Product
from apps.sales.models import CashierSession
from apps.shops.models import Shop
from apps.stocks.models import Stock

User = get_user_model()
PASSWORD = 'Str0ng-Passw0rd!'


class SeedStagingTests(TestCase):

    def seed(self, password=PASSWORD):
        call_command('seed_staging', password=password, verbosity=0, stdout=open(os.devnull, 'w'))

    @patch.dict(os.environ, {'ALLOW_STAGING_SEED': 'false'})
    def test_refuses_to_run_without_the_explicit_flag(self):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(User.objects.exists())
        self.assertFalse(Shop.objects.exists())

    @patch.dict(os.environ, {'ALLOW_STAGING_SEED': 'true'})
    def test_refuses_a_weak_password(self):
        with self.assertRaises(CommandError):
            self.seed(password='1234')
        self.assertFalse(User.objects.exists())

    @patch.dict(os.environ, {'ALLOW_STAGING_SEED': 'true'})
    def test_creates_one_account_per_role_ready_to_log_in(self):
        self.seed()
        self.assertEqual(
            set(User.objects.values_list('role', flat=True)),
            {'SUPER_ADMIN', 'SHOP_MANAGER', 'EMPLOYEE', 'MAGASINIER', 'LIVREUR'},
        )
        self.assertIsNotNone(authenticate(username='caissier@shopm.test', password=PASSWORD))

    @patch.dict(os.environ, {'ALLOW_STAGING_SEED': 'true'})
    def test_manager_runs_both_shops_and_the_cashier_session_is_open(self):
        self.seed()
        manager = User.objects.get(email='manager@shopm.test')
        self.assertEqual(manager.managed_shops.count(), 2)
        session = CashierSession.active_for_shop(manager.shop)
        self.assertEqual(session.cashier.email, 'caissier@shopm.test')

    @patch.dict(os.environ, {'ALLOW_STAGING_SEED': 'true'})
    def test_can_run_twice_without_duplicating(self):
        self.seed()
        self.seed()
        self.assertEqual(User.objects.count(), 6)
        self.assertEqual(Shop.objects.count(), 2)
        self.assertEqual(Product.objects.count(), 5)
        self.assertEqual(Stock.objects.count(), 10)
        self.assertEqual(CashierSession.objects.count(), 1)
