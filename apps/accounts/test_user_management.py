"""
Règles validées pour la gestion des comptes :
seul le Super Admin crée les managers, et un manager ne gère que des employés,
livreurs et magasiniers des boutiques qu'il gère.
"""
from apps.shops.models import Shop

from .test_permissions_baseline import PermissionFixtures, User, make_user


def new_user_body(email, role='EMPLOYEE', shop=None):
    body = {
        'email': email, 'password': 'Str0ng-Passw0rd!', 'password_confirm': 'Str0ng-Passw0rd!',
        'first_name': 'Nouveau', 'last_name': 'Compte', 'role': role,
    }
    if shop is not None:
        body['shop'] = shop.id
    return body


class ManagerCreatesAccountsTests(PermissionFixtures):

    def test_manager_creates_each_staff_role_in_their_shop(self):
        for role in ('EMPLOYEE', 'LIVREUR', 'MAGASINIER'):
            email = f'{role.lower()}-new@test.local'
            response = self.call(self.manager, 'post', '/api/users/', new_user_body(email, role, self.shop_a))
            self.assertEqual(response.status_code, 201, response.content)
            created = User.objects.get(email=email)
            self.assertEqual(created.role, role)
            self.assertEqual(created.home_shop, self.shop_a)

    def test_manager_cannot_create_a_manager(self):
        response = self.call(
            self.manager, 'post', '/api/users/',
            new_user_body('faux-manager@test.local', 'SHOP_MANAGER', self.shop_a),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('role', response.json())
        self.assertFalse(User.objects.filter(email='faux-manager@test.local').exists())

    def test_manager_cannot_create_a_super_admin(self):
        response = self.call(
            self.manager, 'post', '/api/users/',
            new_user_body('faux-admin@test.local', 'SUPER_ADMIN'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email='faux-admin@test.local').exists())

    def test_manager_cannot_create_an_account_in_another_shop(self):
        response = self.call(self.manager, 'post', '/api/users/', new_user_body('ailleurs@test.local', shop=self.shop_b))
        self.assertEqual(response.status_code, 400)
        self.assertIn('shop', response.json())
        self.assertFalse(User.objects.filter(email='ailleurs@test.local').exists())

    def test_multi_shop_manager_creates_in_their_second_shop(self):
        self.shop_b.managers.add(self.manager)
        response = self.call(self.manager, 'post', '/api/users/', new_user_body('second@test.local', shop=self.shop_b))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.get(email='second@test.local').home_shop, self.shop_b)

    def test_super_admin_still_creates_a_manager(self):
        response = self.call(
            self.admin, 'post', '/api/users/',
            new_user_body('vrai-manager@test.local', 'SHOP_MANAGER', self.shop_b),
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(self.shop_b.managers.filter(email='vrai-manager@test.local').exists())


class ManagerUpdatesAccountsTests(PermissionFixtures):

    def patch_target(self, body, user=None):
        return self.call(user or self.manager, 'patch', f'/api/users/{self.target.id}/', body)

    def test_full_escalation_chain_is_blocked(self):
        """Le scénario d'attaque complet : créer un complice, puis le promouvoir."""
        created = self.call(self.manager, 'post', '/api/users/', new_user_body('complice@test.local', shop=self.shop_a))
        self.assertEqual(created.status_code, 201, created.content)
        accomplice = User.objects.get(email='complice@test.local')

        response = self.call(self.manager, 'patch', f'/api/users/{accomplice.id}/', {'role': 'SUPER_ADMIN'})

        self.assertEqual(response.status_code, 400)
        accomplice.refresh_from_db()
        self.assertEqual(accomplice.role, 'EMPLOYEE')

    def test_manager_cannot_promote_to_manager_even_in_their_shop(self):
        response = self.patch_target({'role': 'SHOP_MANAGER'})
        self.assertEqual(response.status_code, 400)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, 'EMPLOYEE')
        self.assertFalse(self.shop_a.managers.filter(id=self.target.id).exists())

    def test_manager_cannot_move_an_account_to_another_shop(self):
        response = self.patch_target({'shop': self.shop_b.id})
        self.assertEqual(response.status_code, 400)
        self.assertIn('shop', response.json())
        self.target.refresh_from_db()
        self.assertEqual(self.target.shop, self.shop_a)

    def test_manager_moves_an_account_between_their_own_shops(self):
        self.shop_b.managers.add(self.manager)
        response = self.patch_target({'shop': self.shop_b.id})
        self.assertEqual(response.status_code, 200, response.content)
        self.target.refresh_from_db()
        self.assertEqual(self.target.shop, self.shop_b)

    def test_manager_changes_role_between_staff_roles(self):
        response = self.patch_target({'role': 'MAGASINIER'})
        self.assertEqual(response.status_code, 200, response.content)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, 'MAGASINIER')

    def test_manager_edits_a_livreur_and_a_magasinier(self):
        for account in (self.livreur, self.magasinier):
            response = self.call(self.manager, 'patch', f'/api/users/{account.id}/', {'first_name': 'Modifié'})
            self.assertEqual(response.status_code, 200, response.content)

    def test_manager_edits_an_employee_of_their_second_shop(self):
        self.shop_b.managers.add(self.manager)
        response = self.call(self.manager, 'patch', f'/api/users/{self.employee_b.id}/', {'first_name': 'Modifié'})
        self.assertEqual(response.status_code, 200, response.content)

    def test_edit_still_works_when_employee_is_temporarily_assigned_elsewhere(self):
        """Le formulaire peut renvoyer la boutique actuelle, même si le manager ne la gère pas."""
        self.target.shop = self.shop_b
        self.target.save(update_fields=['shop'])
        response = self.patch_target({'first_name': 'Modifié', 'shop': self.shop_b.id})
        self.assertEqual(response.status_code, 200, response.content)

    def test_manager_cannot_edit_a_co_manager(self):
        co_manager = make_user('co-manager@test.local', 'SHOP_MANAGER', self.shop_a)
        self.shop_a.managers.add(co_manager)
        response = self.call(self.manager, 'patch', f'/api/users/{co_manager.id}/', {'first_name': 'X'})
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_change_their_own_role(self):
        response = self.call(self.manager, 'patch', f'/api/users/{self.manager.id}/', {'role': 'SUPER_ADMIN'})
        self.assertEqual(response.status_code, 403)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.role, 'SHOP_MANAGER')

    def test_employee_cannot_change_their_own_role(self):
        response = self.call(self.employee, 'patch', f'/api/users/{self.employee.id}/', {'role': 'SUPER_ADMIN'})
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.role, 'EMPLOYEE')
        self.assertEqual(response.status_code, 200)

    def test_super_admin_can_still_change_a_role_and_a_shop(self):
        response = self.patch_target({'role': 'SHOP_MANAGER', 'shop': self.shop_b.id}, user=self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.shop_b.managers.filter(id=self.target.id).exists())


class ManagerOtherAccountActionsTests(PermissionFixtures):

    def test_manager_cannot_deactivate_a_co_manager(self):
        co_manager = make_user('co-manager@test.local', 'SHOP_MANAGER', self.shop_a)
        self.shop_a.managers.add(co_manager)
        response = self.call(self.manager, 'post', f'/api/users/{co_manager.id}/toggle_active/')
        self.assertEqual(response.status_code, 403)
        co_manager.refresh_from_db()
        self.assertTrue(co_manager.is_active)

    def test_manager_cannot_deactivate_themselves(self):
        response = self.call(self.manager, 'post', f'/api/users/{self.manager.id}/toggle_active/')
        self.assertEqual(response.status_code, 403)

    def test_manager_deactivates_a_livreur(self):
        response = self.call(self.manager, 'post', f'/api/users/{self.livreur.id}/toggle_active/')
        self.assertEqual(response.status_code, 200, response.content)
        self.livreur.refresh_from_db()
        self.assertFalse(self.livreur.is_active)

    def test_multi_shop_manager_deactivates_an_employee_of_their_second_shop(self):
        self.shop_b.managers.add(self.manager)
        response = self.call(self.manager, 'post', f'/api/users/{self.employee_b.id}/toggle_active/')
        self.assertEqual(response.status_code, 200, response.content)

    def test_manager_can_only_delete_employees(self):
        response = self.call(self.manager, 'delete', f'/api/users/{self.magasinier.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(id=self.magasinier.id).exists())

    def test_assign_employees_ignores_a_co_manager(self):
        co_manager = make_user('co-manager@test.local', 'SHOP_MANAGER', self.shop_a)
        other_shop = Shop.objects.create(name='Boutique C')
        other_shop.managers.add(self.manager)

        response = self.call(self.manager, 'post', f'/api/shops/{other_shop.id}/assign_employees/', {
            'user_ids': [co_manager.id, self.target.id],
        })

        self.assertEqual(response.status_code, 200, response.content)
        co_manager.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(co_manager.shop, self.shop_a)
        self.assertEqual(self.target.shop, other_shop)
