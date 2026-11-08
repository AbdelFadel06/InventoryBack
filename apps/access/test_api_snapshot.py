"""
Photo de l'API : chaque adresse, appelée par chaque rôle, doit répondre exactement le même
code (200, 400, 403, 404…) qu'au moment de la photo, prise sur le code d'avant les permissions.

Le test passe deux fois : interrupteurs éteints (anciennes règles) puis tous allumés
(grille de permissions). Les deux doivent coller à la photo, case par case.

Reprendre la photo (seulement sur le code d'avant, ou après un changement voulu) :
    SNAPSHOT_WRITE=1 venv/bin/python manage.py test apps.access.test_api_snapshot
"""
import json
import os
from pathlib import Path

from django.core.cache import cache
from django.db import transaction
from django.test import override_settings
from django.urls import get_resolver, reverse

from apps.accounts.test_permissions_baseline import PermissionFixtures
from apps.sales.models import SaleIssue
from apps.stocks.models import StockMovement, StockTransfer

SNAPSHOT = Path(__file__).with_name('api_snapshot.json')
ROLES = ('anonymous', 'admin', 'manager', 'employee', 'magasinier', 'livreur')
SKIPPED = {'api-root'}
METHODS = ('get', 'post', 'put', 'patch', 'delete')


def api_routes():
    """[(nom de route, paramètres, méthodes)] de toutes les adresses /api/."""
    routes = {}

    def walk(patterns, prefix='', namespace=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                inner = f'{namespace}{pattern.namespace}:' if pattern.namespace else namespace
                walk(pattern.url_patterns, prefix + str(pattern.pattern), inner)
                continue
            route = prefix + str(pattern.pattern)
            if not route.startswith('api/') or 'format' in str(pattern.pattern) or pattern.name in SKIPPED \
                    or not pattern.name:
                continue
            callback = pattern.callback
            actions = getattr(callback, 'actions', None)
            if actions:
                # DRF ajoute « head » au fil des appels : seules comptent les méthodes déclarées.
                methods = sorted(m for m in actions if m in METHODS)
            else:
                methods = [m for m in METHODS if hasattr(callback.cls, m)]
            routes[namespace + pattern.name] = (list(pattern.pattern.regex.groupindex), methods)

    walk(get_resolver().url_patterns)
    return sorted((name, params, methods) for name, (params, methods) in routes.items())


class ApiSnapshotTests(PermissionFixtures):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.movement = StockMovement.objects.create(
            product=cls.product, shop=cls.shop_a, location='BOUTIQUE',
            movement_type='entry', quantity=1, created_by=cls.manager,
        )
        cls.transfer = StockTransfer.objects.create(
            product=cls.product, from_shop=cls.shop_a, to_shop=cls.shop_a,
            transfer_type='warehouse', quantity=1, created_by=cls.magasinier,
        )
        cls.issue = SaleIssue.objects.create(sale=cls.sale, reason='wrong_amount', reported_by=cls.employee)

    def object_ids(self):
        return {
            'user': self.target.id, 'shop': self.shop_a.id, 'product': self.product.id,
            'category': self.category.id, 'stock': self.stock.id, 'stock-movement': self.movement.id,
            'stock-transfer': self.transfer.id, 'inventory': self.inventory.id,
            'cashier-session': self.session.id, 'sale': self.sale.id, 'expense': self.expense.id,
            'sale-issue': self.issue.id, 'access-user': self.employee.id,
        }

    def url_for(self, name, params):
        ids = self.object_ids()
        short = name.rsplit(':', 1)[-1]
        kwargs = {}
        for param in params:
            if param == 'pk' or param == 'user_id':
                base = next(b for b in sorted(ids, key=len, reverse=True) if short.startswith(b + '-') or short == b)
                kwargs[param] = ids[base]
            else:
                kwargs[param] = 999999   # ex. image_id : absente, mais le contrôle des droits passe avant
        return reverse(name, kwargs=kwargs)

    def take(self):
        self.client.raise_request_exception = False
        users = {'anonymous': None, 'admin': self.admin, 'manager': self.manager, 'employee': self.employee,
                 'magasinier': self.magasinier, 'livreur': self.livreur}
        result = {}
        for name, params, methods in api_routes():
            url = self.url_for(name, params)
            for method in methods:
                cell = {}
                for role in ROLES:
                    cache.clear()   # anti-abus : 870 appels dépasseraient la limite par minute
                    with transaction.atomic():
                        self.client.force_authenticate(users[role])
                        response = getattr(self.client, method)(url, {}, format='json')
                        transaction.set_rollback(True)   # chaque appel part du même état
                    cell[role] = response.status_code
                result[f'{method.upper()} {name}'] = cell
        return result

    def compare(self, label):
        current = self.take()
        if os.environ.get('SNAPSHOT_WRITE') == '1':
            SNAPSHOT.write_text(json.dumps(current, indent=1, sort_keys=True) + '\n')
            self.skipTest('Photo réécrite')
        expected = json.loads(SNAPSHOT.read_text())
        self.assertEqual(sorted(current), sorted(expected), f'{label} : adresses ajoutées ou retirées')
        differences = [
            f'{endpoint} {role}: photo {expected[endpoint][role]}, maintenant {current[endpoint][role]}'
            for endpoint in expected for role in ROLES
            if expected[endpoint][role] != current[endpoint][role]
        ]
        self.assertEqual(differences, [], f'{label} : écarts avec la photo')

    def test_old_rules_match_the_snapshot(self):
        with override_settings(PERMISSIONS_ENFORCE=[]):
            self.compare('Interrupteurs éteints')

    def test_permission_grid_matches_the_snapshot(self):
        if os.environ.get('SNAPSHOT_WRITE') == '1':
            self.skipTest('Photo prise par le test interrupteurs éteints')
        with override_settings(PERMISSIONS_ENFORCE=['all']):
            self.compare('Interrupteurs allumés')


class GridReallyDecidesTests(ApiSnapshotTests):
    """Interrupteurs allumés et tous les droits retirés : seules les adresses hors grille laissent passer."""

    # Hors grille, voulu : son propre compte, listes d'aide aux écrans, notifications,
    # signalements (traités par le manager), connexion, et la gestion des permissions elle-même.
    UNGATED = {
        'GET accounts:user-me', 'PUT accounts:user-update-profile', 'PATCH accounts:user-update-profile',
        'POST accounts:user-change-password', 'GET accounts:user-managers', 'GET accounts:user-employees',
        'GET accounts:user-livreurs',
        'GET shops:shop-statistics', 'GET shops:shop-staff', 'GET shops:shop-employees',
        'GET shops:shop-assignment-history',
        'GET sales:sale-issue-list', 'GET sales:sale-issue-detail', 'POST sales:sale-issue-resolve',
        'GET push-key', 'POST push-subscribe', 'POST push-unsubscribe', 'POST push-test',
        'GET access-catalog', 'GET access-roles', 'GET access-user', 'PUT access-roles', 'PUT access-user',
        'GET access-switches', 'PUT access-switches', 'GET access-history',
        'POST accounts:password-reset', 'POST accounts:password-reset-confirm',
        'POST token_obtain_pair', 'POST token_refresh',
    }

    def test_old_rules_match_the_snapshot(self):
        self.skipTest('Couvert par ApiSnapshotTests')

    def test_permission_grid_matches_the_snapshot(self):
        self.skipTest('Couvert par ApiSnapshotTests')

    def test_removing_every_right_closes_every_gated_address(self):
        from apps.access.catalog import MANAGE_PERMISSIONS
        from apps.access.models import RolePermission
        RolePermission.objects.exclude(code=MANAGE_PERMISSIONS).update(allowed=False)
        with override_settings(PERMISSIONS_ENFORCE=['all']):
            current = self.take()
        still_open = {
            endpoint for endpoint, cells in current.items()
            if any(200 <= code < 300 or code == 400 for role, code in cells.items() if role != 'anonymous')
        }
        self.assertEqual(sorted(still_open - self.UNGATED), [], 'Adresses qui échappent à la grille')
        self.assertEqual(sorted(self.UNGATED - still_open), [], 'UNGATED cite une adresse qui suit déjà la grille')
