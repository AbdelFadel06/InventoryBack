from rest_framework import permissions


class CanManageInventories(permissions.BasePermission):
    """
    Permission pour gérer les inventaires:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut gérer les inventaires de sa boutique
    - EMPLOYEE: peut compter les produits de sa boutique
    """

    def has_permission(self, request, view):
        # Tout le monde authentifié peut lire
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Création: Super Admin ou Shop Manager
        if view.action == 'create':
            return (request.user and request.user.is_authenticated and
                    (request.user.is_super_admin or request.user.is_shop_manager))

        # Autres actions nécessitent authentification
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_super_admin:
            return True

        if user.is_shop_manager:
            return user.managed_shops.filter(id=obj.shop_id).exists()

        # Employee : accès en lecture + comptage uniquement sur sa boutique
        if user.is_employee:
            if view.action in ['count_product', 'count_multiple'] or request.method in permissions.SAFE_METHODS:
                return obj.shop == user.shop
            return False

        return obj.shop == user.shop


class CanCountInventory(permissions.BasePermission):
    """
    Permission pour compter les produits:
    - Tous les employés de la boutique peuvent compter
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_super_admin:
            return True

        if user.is_shop_manager:
            return user.managed_shops.filter(id=obj.shop_id).exists()

        return obj.shop == user.shop


class CanValidateInventory(permissions.BasePermission):
    """
    Permission pour valider un inventaire:
    - SUPER_ADMIN: peut valider tous les inventaires
    - SHOP_MANAGER: peut valider les inventaires de sa boutique
    """

    def has_permission(self, request, view):
        return (request.user and request.user.is_authenticated and
                (request.user.is_super_admin or request.user.is_shop_manager))

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_super_admin:
            return True

        if user.is_shop_manager:
            return user.managed_shops.filter(id=obj.shop_id).exists()

        return False
