from rest_framework import permissions


class CanManageProducts(permissions.BasePermission):
    """
    Permission pour gérer les produits:
    - SUPER_ADMIN: peut tout gérer (tous les produits)
    - SHOP_MANAGER: peut gérer les produits de sa boutique uniquement
    - EMPLOYEE: lecture seule des produits de sa boutique
    """

    def has_permission(self, request, view):
        # Tout le monde authentifié peut lire
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Création/modification/suppression: Super Admin ou Shop Manager
        return (request.user and request.user.is_authenticated and
                (request.user.is_super_admin or request.user.is_shop_manager))

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Lecture: tout le monde authentifié
        if request.method in permissions.SAFE_METHODS:
            if user.is_super_admin:
                return True
            if obj.shop is None:
                return True
            if user.is_shop_manager:
                return user.managed_shops.filter(id=obj.shop_id).exists()
            return obj.shop_id == user.shop_id

        # Modification/suppression
        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            if obj.shop is None:
                return True
            return user.managed_shops.filter(id=obj.shop_id).exists()

        return False


class CanManageCategories(permissions.BasePermission):
    """
    Permission pour gérer les catégories:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut créer/modifier des catégories
    - EMPLOYEE: lecture seule
    """

    def has_permission(self, request, view):
        # Lecture pour tout le monde authentifié
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Création/modification: Super Admin ou Shop Manager
        return (request.user and request.user.is_authenticated and
                (request.user.is_super_admin or request.user.is_shop_manager))
