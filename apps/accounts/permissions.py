from rest_framework import permissions

# Seuls rôles qu'un manager peut créer ou gérer. Les managers sont créés par le Super Admin.
MANAGER_MANAGEABLE_ROLES = ('EMPLOYEE', 'LIVREUR', 'MAGASINIER')


def manager_can_manage(manager, target):
    """Le manager gère ce compte : rôle autorisé, et rattaché ou affecté à l'une de ses boutiques."""
    if target.role not in MANAGER_MANAGEABLE_ROLES:
        return False
    return manager.managed_shops.filter(id__in=[target.home_shop_id, target.shop_id]).exists()


class IsSuperAdmin(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est Super Admin
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_super_admin


class IsShopManager(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est Manager de boutique
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_shop_manager


class IsShopManagerOrSuperAdmin(permissions.BasePermission):
    """
    Permission pour Manager ou Super Admin
    """
    def has_permission(self, request, view):
        return (request.user and request.user.is_authenticated and
                (request.user.is_super_admin or request.user.is_shop_manager))


class CanManageUser(permissions.BasePermission):
    """
    Permission pour gérer les utilisateurs selon le rôle
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: employés, livreurs et magasiniers des boutiques qu'il gère,
      suppression limitée aux employés
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        if user.is_shop_manager:
            if view.action == 'destroy' and obj.role != 'EMPLOYEE':
                return False
            return manager_can_manage(user, obj)

        # Un utilisateur peut se gérer lui-même (pour update profile)
        if view.action in ['update', 'partial_update']:
            return obj == user

        return False
