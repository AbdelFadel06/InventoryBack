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

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Lecture: voir les inventaires de sa boutique
        if request.method in permissions.SAFE_METHODS:
            return obj.shop == user.shop

        # Modification/suppression
        # Shop Manager peut gérer les inventaires de sa boutique
        if user.is_shop_manager:
            return obj.shop == user.shop

        # Employee peut compter dans les inventaires de sa boutique
        # mais ne peut pas modifier/supprimer
        if user.is_employee:
            if view.action in ['count_product', 'count_multiple']:
                return obj.shop == user.shop
            return False

        return False


class CanCountInventory(permissions.BasePermission):
    """
    Permission pour compter les produits:
    - Tous les employés de la boutique peuvent compter
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Les autres doivent appartenir à la boutique de l'inventaire
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

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Shop Manager peut valider les inventaires de sa boutique
        if user.is_shop_manager:
            return obj.shop == user.shop

        return False
