"""
Remplit une base de staging ou de démo avec des données fictives : deux boutiques,
un compte par rôle, des produits en stock et une session de caisse du jour.

Refuse de tourner sans ALLOW_STAGING_SEED=true, à ne jamais définir en production.
Peut être relancée : elle complète ce qui manque sans dupliquer.

    python manage.py seed_staging --password '<mot de passe de test>'
"""
from decimal import Decimal

from decouple import config
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.products.models import Category, Product
from apps.sales.models import CashierSession
from apps.shops.models import Shop
from apps.stocks.models import Stock

User = get_user_model()

EMAIL_DOMAIN = 'shopm.test'

ACCOUNTS = [
    ('admin',      'SUPER_ADMIN',  None),
    ('manager',    'SHOP_MANAGER', 'A'),
    ('caissier',   'EMPLOYEE',     'A'),
    ('employe',    'EMPLOYEE',     'A'),
    ('magasinier', 'MAGASINIER',   'A'),
    ('livreur',    'LIVREUR',      'A'),
]

PRODUCTS = [
    ('Casserole 24 cm',  'TEST-001', '12500'),
    ('Poêle antiadhésive', 'TEST-002', '9500'),
    ('Service à thé',    'TEST-003', '18000'),
    ('Tapis de salon',   'TEST-004', '35000'),
    ('Rideau occultant', 'TEST-005', '15000'),
]


class Command(BaseCommand):
    help = "Crée des données fictives pour un environnement de staging ou de démo."

    def add_arguments(self, parser):
        parser.add_argument('--password', required=True, help="Mot de passe commun des comptes de test.")

    def handle(self, *args, **options):
        if not config('ALLOW_STAGING_SEED', default=False, cast=bool):
            raise CommandError(
                "Refusé : ALLOW_STAGING_SEED n'est pas activé. "
                "Cette commande ne doit jamais tourner en production."
            )
        try:
            validate_password(options['password'])
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

        with transaction.atomic():
            shops = self._create_shops()
            users = self._create_users(shops, options['password'])
            self._create_catalogue(shops, users['manager'])
            self._open_session(shops['A'], users)

        self.stdout.write(self.style.SUCCESS('Données de test prêtes. Comptes :'))
        for username, role, _ in ACCOUNTS:
            self.stdout.write(f'  {role:<13} {username}@{EMAIL_DOMAIN}')

    def _create_shops(self):
        return {
            key: Shop.objects.get_or_create(name=f'Boutique Test {key}')[0]
            for key in ('A', 'B')
        }

    def _create_users(self, shops, password):
        users = {}
        for username, role, shop_key in ACCOUNTS:
            shop = shops[shop_key] if shop_key else None
            user, _ = User.objects.get_or_create(
                email=f'{username}@{EMAIL_DOMAIN}',
                defaults={
                    'username': f'test-{username}',
                    'first_name': username.capitalize(),
                    'last_name': 'Test',
                    'role': role,
                    'shop': shop,
                    'home_shop': shop,
                    'email_verified': True,
                },
            )
            user.set_password(password)
            user.save()
            users[username] = user

        # Le manager gère les deux boutiques, pour tester le multi-boutiques.
        for shop in shops.values():
            shop.managers.add(users['manager'])
        return users

    def _create_catalogue(self, shops, manager):
        category, _ = Category.objects.get_or_create(name='Catalogue de test', shop=shops['A'])
        for name, sku, price in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    'name': name, 'category': category, 'selling_price': Decimal(price),
                    'shop': shops['A'], 'created_by': manager,
                },
            )
            for location in ('BOUTIQUE', 'MAGASIN'):
                Stock.objects.get_or_create(
                    product=product, shop=shops['A'], location=location,
                    defaults={'quantity': 50},
                )

    def _open_session(self, shop, users):
        if CashierSession.active_for_shop(shop):
            return
        today = timezone.localdate()
        CashierSession.objects.create(
            shop=shop, cashier=users['caissier'], created_by=users['manager'],
            start_date=today, end_date=today,
        )
