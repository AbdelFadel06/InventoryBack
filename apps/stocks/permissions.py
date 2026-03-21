from rest_framework import permissions


class CanManageStock(permissions.BasePermission):
    """
    Permission pour gérer les stocks:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut gérer les stocks de sa boutique
    - EMPLOYEE: peut voir les stocks de sa boutique, mais pas modifier
    """

    def has_permission(self, request, view):
        # Lecture pour tous les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Création/modification: Super Admin ou Shop Manager
        return (request.user and request.user.is_authenticated and
                (request.user.is_super_admin or request.user.is_shop_manager))

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Lecture
        if request.method in permissions.SAFE_METHODS:
            # Super Admin voit tout
            if user.is_super_admin:
                return True

            # Les autres voient que les stocks de leur boutique
            return obj.shop == user.shop

        # Modification/suppression
        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Shop Manager peut gérer les stocks de sa boutique
        if user.is_shop_manager:
            return obj.shop == user.shop

        return False


class CanCreateStockMovement(permissions.BasePermission):
    """
    Permission pour créer des mouvements de stock:
    - SUPER_ADMIN: tous les mouvements
    - SHOP_MANAGER: mouvements de sa boutique
    - EMPLOYEE: peut enregistrer des ventes (exit) uniquement
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Les autres ne peuvent voir que les mouvements de leur boutique
        return obj.shop == user.shop


class CanManageTransfers(permissions.BasePermission):
    """
    Permission pour gérer les transferts:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut créer des transferts depuis sa boutique
                    peut recevoir des transferts vers sa boutique
    - EMPLOYEE: lecture seule
    """

    def has_permission(self, request, view):
        # Lecture pour tous les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Création: Super Admin ou Shop Manager
        return (request.user and request.user.is_authenticated and
                (request.user.is_super_admin or request.user.is_shop_manager))

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Lecture
        if request.method in permissions.SAFE_METHODS:
            # Super Admin voit tout
            if user.is_super_admin:
                return True

            # Les autres voient les transferts concernant leur boutique
            return obj.from_shop == user.shop or obj.to_shop == user.shop

        # Modification (ex: recevoir un transfert)
        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Shop Manager peut gérer les transferts de/vers sa boutique
        if user.is_shop_manager:
            return obj.from_shop == user.shop or obj.to_shop == user.shop

        return False
