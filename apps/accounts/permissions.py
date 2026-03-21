from rest_framework import permissions


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
    - SHOP_MANAGER: peut gérer les utilisateurs de sa boutique uniquement
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Shop Manager peut gérer les utilisateurs de sa boutique
        if user.is_shop_manager:
            # Peut gérer que les employés de sa boutique
            return (obj.shop == user.shop and
                    obj.role == 'EMPLOYEE')

        # Un utilisateur peut se gérer lui-même (pour update profile)
        if view.action in ['update', 'partial_update']:
            return obj == user

        return False
