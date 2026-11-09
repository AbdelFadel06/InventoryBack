"""
Remplit l'instance de DÉMO publique avec une boutique fictive mais crédible :
catalogue aux prix en F CFA, stocks (dont quelques ruptures), 30 jours de ventes,
livraisons, dépenses, transferts, un inventaire validé et un signalement ouvert.

Refuse de tourner sans ALLOW_DEMO_SEED=true, à ne JAMAIS définir en production.

    python manage.py seed_demo --password '<mot de passe public de la démo>'
    python manage.py seed_demo --reset   # chaque nuit : vide la base puis recrée tout (DEMO_PASSWORD du .env)

Les données sont tirées au hasard avec une graine fixe : chaque nuit, la démo repart
du même état, décalé au jour courant.
"""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from decouple import config
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.inventories.models import Inventory, InventoryLine
from apps.products.models import Category, Product
from apps.sales.models import CashierSession, Expense, Sale, SaleIssue, SaleItem
from apps.shops.models import Shop
from apps.stocks.models import Stock, StockMovement, StockTransfer

User = get_user_model()

DOMAIN = 'shopm.demo'
DAYS = 30

SHOPS = {
    'main': {'name': 'Maison Akwaba', 'slogan': 'Tout pour la maison', 'city': 'Cotonou',
             'address': 'Carré 214, Haie Vive', 'phone_number': '+22901970000000'},
    'second': {'name': 'Maison Akwaba — Porto-Novo', 'slogan': 'Tout pour la maison', 'city': 'Porto-Novo',
               'address': 'Avenue Jean-Paul II, Ouando', 'phone_number': '+22901970000001'},
}

# (identifiant, rôle, prénom, nom)
ACCOUNTS = [
    ('manager',    'SHOP_MANAGER', 'Aïcha',  'Dossou'),
    ('caisse',     'EMPLOYEE',     'Koffi',  'Agbo'),
    ('vendeuse',   'EMPLOYEE',     'Mariam', 'Sanni'),
    ('magasinier', 'MAGASINIER',   'Rachid', 'Bello'),
    ('livreur',    'LIVREUR',      'Serge',  'Houngbo'),
]

# catégorie → [(nom, prix F CFA, unité)]
CATALOGUE = {
    'Cuisine': [
        ('Casserole inox 24 cm', 12500, 'pièce'), ('Poêle antiadhésive 28 cm', 9500, 'pièce'),
        ('Marmite en fonte 6 L', 27500, 'pièce'), ('Set de 6 couteaux', 15000, 'lot'),
        ('Planche à découper bambou', 4500, 'pièce'), ('Service à thé 12 pièces', 18000, 'lot'),
        ('Verres à eau (x6)', 6000, 'lot'), ('Assiettes plates (x6)', 9000, 'lot'),
        ('Thermos 1,5 L', 7500, 'pièce'), ('Bassine plastique 40 L', 3500, 'pièce'),
    ],
    'Électroménager': [
        ('Mixeur 1,5 L', 22000, 'pièce'), ('Bouilloire électrique 1,7 L', 13500, 'pièce'),
        ('Ventilateur sur pied', 25000, 'pièce'), ('Fer à repasser vapeur', 14000, 'pièce'),
        ('Réchaud à gaz 2 feux', 32000, 'pièce'), ('Cuiseur à riz 1,8 L', 19500, 'pièce'),
    ],
    'Linge de maison': [
        ('Drap 2 places', 11000, 'pièce'), ('Serviette de bain', 5500, 'pièce'),
        ('Rideau occultant', 15000, 'pièce'), ('Nappe 6 couverts', 8500, 'pièce'),
        ('Moustiquaire imprégnée', 6500, 'pièce'), ('Oreiller', 6000, 'pièce'),
    ],
    'Maison & déco': [
        ('Tapis de salon 160x230', 35000, 'pièce'), ('Miroir mural', 16000, 'pièce'),
        ('Lampe de chevet', 9500, 'pièce'), ('Horloge murale', 7000, 'pièce'),
        ('Panier de rangement', 4000, 'pièce'), ('Pot de fleurs céramique', 5000, 'pièce'),
    ],
    'Entretien': [
        ('Balai et pelle', 3000, 'lot'), ('Seau essoreur', 6500, 'pièce'),
        ('Savon liquide 5 L', 4500, 'bidon'), ('Éponges (x10)', 1500, 'lot'),
        ('Désodorisant', 2000, 'pièce'), ('Gants de ménage', 1000, 'paire'),
    ],
}

# Produits volontairement en rupture ou en stock bas à la fin, pour les alertes.
OUT_OF_STOCK = ('Marmite en fonte 6 L', 'Moustiquaire imprégnée')
LOW_STOCK = ('Ventilateur sur pied', 'Savon liquide 5 L', 'Service à thé 12 pièces')

EXPENSES = [('Transport marchandises', 5000), ('Électricité', 15000), ('Sachets et emballages', 3000),
            ('Crédit téléphone', 2000), ('Eau', 1500), ('Réparation étagère', 7500)]


def at(day, hour, minute):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class Command(BaseCommand):
    help = "Crée (ou recrée avec --reset) les données de la démo publique."

    def add_arguments(self, parser):
        parser.add_argument('--password', default=None,
                            help="Mot de passe public des comptes démo (sinon DEMO_PASSWORD du .env).")
        parser.add_argument('--reset', action='store_true', help="Vide entièrement la base avant de recréer.")

    def handle(self, *args, **options):
        if not config('ALLOW_DEMO_SEED', default=False, cast=bool):
            raise CommandError(
                "Refusé : ALLOW_DEMO_SEED n'est pas activé. Cette commande ne doit jamais tourner en production."
            )
        options['password'] = options['password'] or config('DEMO_PASSWORD', default='')
        if not options['password']:
            raise CommandError("Mot de passe manquant : --password ou DEMO_PASSWORD dans le .env.")
        try:
            validate_password(options['password'])
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

        if options['reset']:
            call_command('flush', interactive=False, verbosity=0)
            self._restore_permission_grid()
        elif Shop.objects.exists():
            raise CommandError("La base contient déjà des boutiques : relancez avec --reset pour repartir de zéro.")

        self.random = random.Random(2026)
        self.today = timezone.localdate()
        with transaction.atomic():
            shops = self._shops()
            users = self._users(shops, options['password'])
            products = self._catalogue(shops['main'], users['manager'])
            self._initial_stock(shops['main'], products, users['magasinier'])
            self._history(shops['main'], products, users)
            self._transfers(shops['main'], products, users)
            self._inventory(shops['main'], products, users)
            self._final_alerts(shops['main'], products, users['manager'])
            self._open_issue(shops['main'], users)

        self.stdout.write(self.style.SUCCESS('Démo prête. Comptes :'))
        for username, role, first, last in ACCOUNTS:
            self.stdout.write(f'  {role:<13} demo.{username}@{DOMAIN}  ({first} {last})')

    # ── Grille des permissions (vidée par flush) ───────────────────────────
    def _restore_permission_grid(self):
        from apps.access.catalog import PERMISSIONS, ROLES
        from apps.access.models import RolePermission
        RolePermission.objects.bulk_create(
            [RolePermission(role=r, code=p.code, allowed=r in p.default_roles) for p in PERMISSIONS for r in ROLES],
            ignore_conflicts=True,
        )

    # ── Boutiques et comptes ───────────────────────────────────────────────
    def _shops(self):
        return {key: Shop.objects.create(**fields) for key, fields in SHOPS.items()}

    def _users(self, shops, password):
        users = {}
        for username, role, first, last in ACCOUNTS:
            user = User.objects.create(
                email=f'demo.{username}@{DOMAIN}', username=f'demo-{username}',
                first_name=first, last_name=last, role=role,
                shop=shops['main'], home_shop=shops['main'], email_verified=True,
            )
            user.set_password(password)
            user.save()
            users[username] = user
        for shop in shops.values():
            shop.managers.add(users['manager'])
        return users

    # ── Catalogue et stock de départ ───────────────────────────────────────
    def _catalogue(self, shop, manager):
        products = []
        number = 1
        for category_name, items in CATALOGUE.items():
            category = Category.objects.create(name=category_name, shop=shop)
            for name, price, unit in items:
                products.append(Product.objects.create(
                    name=name, sku=f'AKW-{number:03d}', barcode=f'61{number:011d}',
                    category=category, selling_price=Decimal(price), unit=unit,
                    minimum_stock=3, reorder_level=8, shop=shop, created_by=manager,
                ))
                number += 1
        return products

    def _movement(self, when, **fields):
        movement = StockMovement.objects.create(**fields)
        StockMovement.objects.filter(id=movement.id).update(created_at=when)
        return movement

    def _initial_stock(self, shop, products, magasinier):
        arrival = at(self.today - timedelta(days=DAYS + 2), 9, 0)
        for product in products:
            for location, (low, high) in (('BOUTIQUE', (25, 60)), ('MAGASIN', (40, 120))):
                self._movement(
                    arrival, product=product, shop=shop, location=location, movement_type='entry',
                    quantity=self.random.randint(low, high), reason='Arrivage fournisseur',
                    reference='ARR-DEMO-001', created_by=magasinier,
                )

    # ── 30 jours d'activité ────────────────────────────────────────────────
    def _history(self, shop, products, users):
        cashiers = [users['caisse'], users['vendeuse']]
        weights = [self.random.randint(1, 10) for _ in products]   # produits plus ou moins demandés
        for offset in range(DAYS, -1, -1):
            day = self.today - timedelta(days=offset)
            cashier = cashiers[offset % 2]
            session = CashierSession.objects.create(
                shop=shop, cashier=cashier, created_by=users['manager'], start_date=day, end_date=day,
                status='active' if offset == 0 else 'closed',
                closed_at=None if offset == 0 else at(day, 20, 30),
            )
            self._restock(shop, day, users['magasinier'])
            busy = day.weekday() == 5   # le samedi est plus chargé
            count = self.random.randint(14, 24) if busy else self.random.randint(6, 15)
            if offset == 0:
                now = timezone.localtime()
                count = max(2, min(count, (now.hour - 8) * 2)) if now.hour >= 9 else 2
            for _ in range(count):
                self._sale(shop, session, cashier, day, products, weights, users)
            if self.random.random() < 0.4:
                label, amount = self.random.choice(EXPENSES)
                Expense.objects.create(session=session, shop=shop, label=label, amount=Decimal(amount),
                                       created_by=cashier, sale_date=day)

    def _restock(self, shop, day, magasinier):
        """Chaque matin, le rayon presque vide est réapprovisionné : depuis le magasin, sinon par un arrivage."""
        moment = at(day, 7, 45)
        reference = f'REA-{day:%Y%m%d}'
        for stock in Stock.objects.filter(shop=shop, location='BOUTIQUE', quantity__lt=8).select_related('product'):
            product = stock.product
            in_warehouse = Stock.objects.get(product=product, shop=shop, location='MAGASIN').quantity
            quantity = min(self.random.randint(20, 35), in_warehouse)
            if quantity > 0:
                self._movement(moment, product=product, shop=shop, location='MAGASIN', movement_type='transfer_out',
                               quantity=-quantity, reference=reference, reason='Réassort du rayon',
                               created_by=magasinier)
                self._movement(moment, product=product, shop=shop, location='BOUTIQUE', movement_type='transfer_in',
                               quantity=quantity, reference=reference, reason='Réassort du rayon',
                               created_by=magasinier)
            else:
                self._movement(moment, product=product, shop=shop, location='BOUTIQUE', movement_type='entry',
                               quantity=self.random.randint(20, 35), reference=reference,
                               reason='Arrivage fournisseur', created_by=magasinier)

    def _sale(self, shop, session, cashier, day, products, weights, users):
        lines = {}
        for product in self.random.choices(products, weights=weights, k=self.random.choice((1, 1, 2, 2, 3, 4))):
            lines[product] = lines.get(product, 0) + self.random.choice((1, 1, 1, 2, 3))
        available = {s.product_id: s.quantity for s in Stock.objects.filter(
            shop=shop, location='BOUTIQUE', product__in=list(lines))}
        lines = {p: q for p, q in lines.items() if available.get(p.id, 0) >= q}
        if not lines:
            return

        delivery = self.random.random() < 0.15
        moment = at(day, self.random.randint(8, 19), self.random.randint(0, 59))
        if day == self.today:
            moment = min(moment, timezone.now() - timedelta(minutes=5))
        sale = Sale.objects.create(
            session=session, shop=shop, cashier=cashier,
            sale_type='delivery' if delivery else 'direct',
            payment_method='on_delivery' if delivery else self.random.choice(('cash', 'cash', 'mobile_money')),
            payment_status='paid',
            livreur=users['livreur'] if delivery else None,
            delivery_address=self.random.choice(('Fidjrossè, rue 12', 'Akpakpa, Sègbèya', 'Cadjèhoun, von Pharmacie')) if delivery else None,
            client_phone='+22901960000' + str(self.random.randint(10, 99)) if delivery else None,
            delivered_at=moment + timedelta(hours=2) if delivery else None,
            livreur_paid=delivery and day < self.today - timedelta(days=2),
        )
        for product, quantity in lines.items():
            discount = self.random.random() < 0.1
            SaleItem.objects.create(
                sale=sale, product=product, quantity=quantity, unit_price=product.selling_price,
                discount_type='percent' if discount else None, discount_value=Decimal(10 if discount else 0),
            )
            self._movement(moment, product=product, shop=shop, location='BOUTIQUE', movement_type='exit',
                           quantity=-quantity, reference=sale.reference, reason=f'Vente {sale.reference}',
                           created_by=cashier)
        sale.recalculate_totals()
        Sale.objects.filter(id=sale.id).update(created_at=moment)

    # ── Transferts magasin → boutique ──────────────────────────────────────
    def _transfers(self, shop, products, users):
        for number, offset in enumerate((20, 9, 3), start=1):
            day = self.today - timedelta(days=offset)
            quantity = self.random.choice((10, 15, 20))
            stocked = [s.product for s in Stock.objects.filter(
                shop=shop, location='MAGASIN', quantity__gte=quantity).select_related('product')]
            if not stocked:
                continue
            product = self.random.choice(sorted(stocked, key=lambda p: p.id))
            transfer = StockTransfer.objects.create(
                reference=f'TRF-DEMO-{number:03d}', transfer_type='warehouse', from_shop=shop, to_shop=shop,
                product=product, quantity=quantity, status='received', created_by=users['magasinier'],
                sent_at=at(day, 10, 0), received_at=at(day, 11, 30), received_by=users['manager'],
            )
            StockTransfer.objects.filter(id=transfer.id).update(created_at=at(day, 9, 45))
            for location, movement_type, sign, who in (('MAGASIN', 'transfer_out', -1, 'magasinier'),
                                                       ('BOUTIQUE', 'transfer_in', 1, 'manager')):
                self._movement(at(day, 10, 0), product=product, shop=shop, location=location,
                               movement_type=movement_type, quantity=sign * quantity,
                               reference=transfer.reference, reason='Transfert magasin → boutique',
                               created_by=users[who])
        StockTransfer.objects.create(
            reference='TRF-DEMO-004', transfer_type='warehouse', from_shop=shop, to_shop=shop,
            product=products[3], quantity=12, status='pending', created_by=users['magasinier'],
        )

    # ── Inventaire validé la semaine dernière ──────────────────────────────
    def _inventory(self, shop, products, users):
        day = self.today - timedelta(days=7)
        inventory = Inventory.objects.create(
            reference='INV-DEMO-001', shop=shop, inventory_date=day, status='validated',
            notes='Inventaire mensuel du rayon cuisine', created_by=users['manager'],
            completed_at=at(day, 18, 0), validated_at=at(day, 18, 30), validated_by=users['manager'],
        )
        for product in products[:10]:
            stock = Stock.objects.get(product=product, shop=shop, location='BOUTIQUE')
            InventoryLine.objects.create(
                inventory=inventory, product=product, expected_quantity=stock.quantity,
                counted_quantity=stock.quantity - (1 if product.name == 'Thermos 1,5 L' else 0),
                counted_by=users['vendeuse'],
            )

    # ── Alertes visibles dans la cloche et sur la page Stocks ──────────────
    def _final_alerts(self, shop, products, manager):
        by_name = {p.name: p for p in products}
        targets = [(name, 0) for name in OUT_OF_STOCK] + [(name, 2) for name in LOW_STOCK]
        moment = timezone.now() - timedelta(hours=3)
        for name, wanted in targets:
            stock = Stock.objects.get(product=by_name[name], shop=shop, location='BOUTIQUE')
            if stock.quantity != wanted:
                self._movement(moment, product=by_name[name], shop=shop, location='BOUTIQUE',
                               movement_type='adjustment', quantity=wanted - stock.quantity,
                               reason='Ajustement après comptage', created_by=manager)

    def _open_issue(self, shop, users):
        sale = Sale.objects.filter(shop=shop, created_at__date=self.today).order_by('-created_at').first()
        if sale:
            SaleIssue.objects.create(sale=sale, reason='wrong_amount', comment='Le client dit avoir payé 500 F de plus.',
                                     reported_by=sale.cashier)
