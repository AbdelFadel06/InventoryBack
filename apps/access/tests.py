"""Tables de permissions : valeurs de départ = comportement actuel, calcul des droits, accès réservé."""
from django.test import TestCase

from apps.accounts.test_permissions_baseline import MATRIX, PermissionFixtures

from .catalog import BY_CODE, MANAGE_PERMISSIONS, PERMISSIONS, ROLES
from .models import RolePermission, UserPermission
from .services import effective_permissions, forget_permissions, has_perm

# Ligne de la grille de référence → droit du catalogue qui la couvre.
MATRIX_TO_CODE = {
    'users_list': 'users.view', 'users_create': 'users.create', 'users_update': 'users.update',
    'users_delete': 'users.delete', 'users_toggle_active': 'users.toggle_active',
    'shops_list': 'shops.view', 'shops_create': 'shops.create', 'shops_update': 'shops.update',
    'shops_delete': 'shops.delete', 'shops_assign_manager': 'shops.assign_manager',
    'shops_assign_employees': 'shops.assign_staff',
    'products_list': 'products.view', 'products_create': 'products.create', 'products_update': 'products.update',
    'products_delete': 'products.delete', 'products_bulk_update_prices': 'products.bulk_prices',
    'categories_create': 'categories.manage',
    'stocks_list': 'stock.view', 'stocks_adjust': 'stock.adjust_warehouse',
    'stocks_adjust_boutique': 'stock.adjust_boutique', 'movements_add_stock': 'stock.movements',
    'movements_remove_stock': 'stock.movements', 'transfers_create': 'transfers.create',
    'inventories_list': 'inventories.view', 'inventories_create': 'inventories.create',
    'inventories_count': 'inventories.count', 'inventories_validate': 'inventories.validate',
    'inventories_complete': 'inventories.validate', 'inventories_cancel': 'inventories.cancel',
    'inventories_delete': 'inventories.cancel',
    'sales_list': 'sales.view', 'sales_livreur_point': 'sales.view', 'sales_create': 'sales.create',
    'sales_daily_report': 'reports.view', 'sales_period_report': 'reports.view',
    'sales_monthly_summary': 'reports.view', 'sales_livreur_stats': 'reports.view',
    'sales_cancel': 'sales.cancel', 'sales_modify_items': 'deliveries.modify',
    'sales_mark_delivered': 'deliveries.mark_delivered', 'sales_validate_payment': 'deliveries.validate_payment',
    'sales_mark_livreur_paid': 'deliveries.pay_livreur',
    'sessions_list': 'sessions.view', 'sessions_create': 'sessions.manage', 'sessions_close': 'sessions.manage',
    'sessions_delete_empty': 'sessions.manage',
    'expenses_list': 'expenses.view', 'expenses_create': 'expenses.create', 'expenses_delete': 'expenses.delete',
}
BASELINE_ROLE = {'admin': 'SUPER_ADMIN', 'manager': 'SHOP_MANAGER', 'employee': 'EMPLOYEE',
                 'livreur': 'LIVREUR', 'magasinier': 'MAGASINIER'}


class CatalogMatchesTodayTests(TestCase):

    def test_every_baseline_row_is_covered(self):
        self.assertEqual({row[0] for row in MATRIX} - set(MATRIX_TO_CODE), set())

    def test_defaults_reproduce_the_current_api_rights(self):
        for name, _method, _url, _data, allowed in MATRIX:
            expected = {BASELINE_ROLE[r] for r in allowed}
            self.assertEqual(set(BY_CODE[MATRIX_TO_CODE[name]].default_roles), expected, name)

    def test_seed_fills_the_whole_grid(self):
        self.assertEqual(RolePermission.objects.count(), len(PERMISSIONS) * len(ROLES))
        for permission in PERMISSIONS:
            for role in ROLES:
                self.assertEqual(
                    RolePermission.objects.get(role=role, code=permission.code).allowed,
                    role in permission.default_roles, f'{role} {permission.code}',
                )


class EffectivePermissionTests(PermissionFixtures):

    def fresh(self, user):
        user.refresh_from_db()
        forget_permissions(user)
        return user

    def test_role_grid_decides(self):
        self.assertTrue(has_perm(self.fresh(self.manager), 'sales.cancel'))
        self.assertFalse(has_perm(self.fresh(self.employee), 'sales.cancel'))
        RolePermission.objects.filter(role='EMPLOYEE', code='sales.cancel').update(allowed=True)
        self.assertTrue(has_perm(self.fresh(self.employee), 'sales.cancel'))

    def test_personal_exception_adds_or_removes(self):
        UserPermission.objects.create(user=self.employee, code='sales.cancel', allowed=True)
        UserPermission.objects.create(user=self.manager, code='products.update', allowed=False)
        self.assertTrue(has_perm(self.fresh(self.employee), 'sales.cancel'))
        self.assertFalse(has_perm(self.fresh(self.manager), 'products.update'))
        # Les autres employés gardent la règle de leur rôle.
        self.assertFalse(has_perm(self.fresh(self.target), 'sales.cancel'))

    def test_super_admin_can_never_lock_himself_out(self):
        RolePermission.objects.filter(role='SUPER_ADMIN', code=MANAGE_PERMISSIONS).update(allowed=False)
        UserPermission.objects.create(user=self.admin, code=MANAGE_PERMISSIONS, allowed=False)
        self.assertTrue(has_perm(self.fresh(self.admin), MANAGE_PERMISSIONS))

    def test_super_admin_does_not_register_sales(self):
        self.assertFalse(has_perm(self.fresh(self.admin), 'sales.create'))

    def test_inactive_account_has_no_right(self):
        self.employee.is_active = False
        self.employee.save()
        self.assertFalse(any(effective_permissions(self.fresh(self.employee)).values()))

    def test_unknown_code_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            has_perm(self.manager, 'n.existe.pas')


class PermissionApiTests(PermissionFixtures):

    def test_only_the_super_admin_reads_permissions(self):
        for url in ('/api/access/catalog/', '/api/access/roles/', f'/api/access/users/{self.employee.id}/'):
            self.assertEqual(self.call(self.admin, 'get', url).status_code, 200, url)
            for user in (self.manager, self.employee, self.magasinier, self.livreur):
                self.assertEqual(self.call(user, 'get', url).status_code, 403, f'{url} {user.email}')

    def test_grid_and_user_view(self):
        grid = self.call(self.admin, 'get', '/api/access/roles/').json()
        self.assertTrue(grid['SHOP_MANAGER']['sales.cancel'])
        self.assertFalse(grid['LIVREUR']['reports.view'])
        UserPermission.objects.create(user=self.employee, code='sales.cancel', allowed=True)
        body = self.call(self.admin, 'get', f'/api/access/users/{self.employee.id}/').json()
        self.assertTrue(body['effective']['sales.cancel'])
        self.assertEqual(body['overrides'], {'sales.cancel': True})


class SwitchTests(PermissionFixtures):
    """Un interrupteur par module : allumer l'un ne change rien aux autres."""

    def setUp(self):
        super().setUp()
        RolePermission.objects.filter(role='SHOP_MANAGER', code__in=['products.create', 'sales.cancel']).update(allowed=False)

    def create_product(self):
        return self.call(self.manager, 'post', '/api/products/', {
            'name': 'Nouveau', 'sku': 'SKU-NEW', 'category': self.category.id, 'selling_price': 100,
        })

    def test_switches_off_keep_the_old_rules(self):
        from django.test import override_settings
        with override_settings(PERMISSIONS_ENFORCE=[]):
            self.assertEqual(self.create_product().status_code, 201)

    def test_only_the_switched_module_follows_the_grid(self):
        from django.test import override_settings
        with override_settings(PERMISSIONS_ENFORCE=['produits']):
            self.assertEqual(self.create_product().status_code, 403)
            # Ventes : interrupteur éteint, l'ancienne règle s'applique encore (motif manquant → 400, pas 403).
            response = self.call(self.manager, 'post', f'/api/sales/{self.sale.id}/cancel/', {})
            self.assertNotEqual(response.status_code, 403)

    def test_own_profile_stays_editable_without_any_right(self):
        from django.test import override_settings
        RolePermission.objects.exclude(code=MANAGE_PERMISSIONS).update(allowed=False)
        with override_settings(PERMISSIONS_ENFORCE=['all']):
            response = self.call(self.employee, 'patch', f'/api/users/{self.employee.id}/', {'first_name': 'Awa'})
        self.assertEqual(response.status_code, 200, response.content)


class PermissionScreenApiTests(PermissionFixtures):
    """Écran des permissions : modifications par le Super Admin seul, toutes journalisées."""

    def put(self, user, url, data):
        return self.call(user, 'put', url, data)

    def test_role_cell_change_is_logged_and_applied(self):
        from .models import PermissionChange
        response = self.put(self.admin, '/api/access/roles/', {'role': 'EMPLOYEE', 'code': 'sales.cancel', 'allowed': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(RolePermission.objects.get(role='EMPLOYEE', code='sales.cancel').allowed)
        change = PermissionChange.objects.get()
        self.assertEqual((change.role, change.code, change.before, change.after), ('EMPLOYEE', 'sales.cancel', False, True))
        # Même valeur une seconde fois : rien de plus au journal.
        self.put(self.admin, '/api/access/roles/', {'role': 'EMPLOYEE', 'code': 'sales.cancel', 'allowed': True})
        self.assertEqual(PermissionChange.objects.count(), 1)

    def test_super_admin_cannot_remove_his_own_permission_management(self):
        response = self.put(self.admin, '/api/access/roles/', {'role': 'SUPER_ADMIN', 'code': MANAGE_PERMISSIONS, 'allowed': False})
        self.assertEqual(response.status_code, 400)
        response = self.put(self.admin, f'/api/access/users/{self.admin.id}/', {'code': MANAGE_PERMISSIONS, 'allowed': False})
        self.assertEqual(response.status_code, 400)

    def test_personal_exception_set_then_cleared(self):
        url = f'/api/access/users/{self.employee.id}/'
        body = self.put(self.admin, url, {'code': 'sales.cancel', 'allowed': True}).json()
        self.assertTrue(body['effective']['sales.cancel'])
        self.assertEqual(body['overrides'], {'sales.cancel': True})
        body = self.put(self.admin, url, {'code': 'sales.cancel', 'allowed': None}).json()
        self.assertFalse(body['effective']['sales.cancel'])
        self.assertEqual(body['overrides'], {})

    def test_invalid_values_are_refused(self):
        for data in ({'role': 'X', 'code': 'sales.cancel', 'allowed': True},
                     {'role': 'EMPLOYEE', 'code': 'nope', 'allowed': True},
                     {'role': 'EMPLOYEE', 'code': 'sales.cancel', 'allowed': 'oui'}):
            self.assertEqual(self.put(self.admin, '/api/access/roles/', data).status_code, 400, data)

    def test_switch_from_the_screen_takes_effect_and_is_logged(self):
        from .models import PermissionChange
        RolePermission.objects.filter(role='SHOP_MANAGER', code='products.create').update(allowed=False)
        create = lambda: self.call(self.manager, 'post', '/api/products/', {
            'name': 'Nouveau', 'sku': 'SKU-NEW', 'category': self.category.id, 'selling_price': 100})
        self.assertEqual(create().status_code, 201)   # interrupteur éteint : ancienne règle

        body = self.put(self.admin, '/api/access/switches/', {'module': 'produits', 'enabled': True}).json()
        produits = next(m for m in body['modules'] if m['module'] == 'produits')
        self.assertTrue(produits['enabled'] and produits['effective'])
        self.call(self.manager, 'get', '/api/products/')   # nouvelle requête
        self.assertEqual(create().status_code, 403)   # la grille décide
        self.assertTrue(PermissionChange.objects.filter(code='interrupteur:produits', after=True).exists())

    def test_emergency_stop_forces_the_old_rules(self):
        from django.test import override_settings
        from .services import forget_switches
        RolePermission.objects.filter(role='SHOP_MANAGER', code='products.create').update(allowed=False)
        self.put(self.admin, '/api/access/switches/', {'module': 'produits', 'enabled': True})
        with override_settings(PERMISSIONS_FORCE_OLD=True):
            forget_switches()
            response = self.call(self.manager, 'post', '/api/products/', {
                'name': 'Nouveau', 'sku': 'SKU-NEW2', 'category': self.category.id, 'selling_price': 100})
            self.assertEqual(response.status_code, 201)
            switches = self.call(self.admin, 'get', '/api/access/switches/').json()
            self.assertTrue(switches['emergency_stop'])
            self.assertFalse(next(m for m in switches['modules'] if m['module'] == 'produits')['effective'])

    def test_history_lists_changes(self):
        self.put(self.admin, '/api/access/roles/', {'role': 'EMPLOYEE', 'code': 'sales.cancel', 'allowed': True})
        self.put(self.admin, '/api/access/switches/', {'module': 'ventes', 'enabled': True})
        rows = self.call(self.admin, 'get', '/api/access/history/').json()
        self.assertEqual(len(rows), 2)
        self.assertIn('Caisse, ventes et livraisons', rows[0]['label'])
        self.assertEqual(rows[1]['label'], 'Annuler une vente (avec motif)')

    def test_only_the_super_admin_writes(self):
        for user in (self.manager, self.employee, self.magasinier, self.livreur):
            self.assertEqual(self.put(user, '/api/access/roles/', {'role': 'EMPLOYEE', 'code': 'sales.cancel', 'allowed': True}).status_code, 403)
            self.assertEqual(self.put(user, '/api/access/switches/', {'module': 'ventes', 'enabled': True}).status_code, 403)
            self.assertEqual(self.call(user, 'get', '/api/access/history/').status_code, 403)
