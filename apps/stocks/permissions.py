from rest_framework import permissions


class CanManageStock(permissions.BasePermission):
    """
    - SUPER_ADMIN   : tout
    - SHOP_MANAGER  : stocks de sa boutique (lecture + écriture)
    - MAGASINIER    : stocks de sa boutique (lecture + écriture stock MAGASIN uniquement)
    - EMPLOYEE/LIVREUR : lecture seule
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_super_admin or request.user.is_shop_manager or request.user.is_magasinier

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in permissions.SAFE_METHODS:
            if user.is_super_admin:
                return True
            return obj.shop == user.shop

        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            return obj.shop == user.shop
        if user.is_magasinier:
            return obj.shop == user.shop and obj.location == 'MAGASIN'
        return False


class CanCreateStockMovement(permissions.BasePermission):
    """
    - SUPER_ADMIN  : tous les mouvements
    - SHOP_MANAGER : mouvements de sa boutique
    - MAGASINIER   : entrées/ajustements sur le stock MAGASIN de sa boutique
    - EMPLOYEE     : peut enregistrer des ventes (exit) uniquement
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_super_admin:
            return True
        return obj.shop == user.shop


class CanManageTransfers(permissions.BasePermission):
    """
    - SUPER_ADMIN  : tout
    - SHOP_MANAGER : créer, envoyer, recevoir les transferts de/vers sa boutique
    - MAGASINIER   : créer et envoyer les transferts warehouse→boutique de sa boutique
    - EMPLOYEE     : lecture seule
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_super_admin or request.user.is_shop_manager or request.user.is_magasinier

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in permissions.SAFE_METHODS:
            if user.is_super_admin:
                return True
            return obj.from_shop == user.shop or obj.to_shop == user.shop

        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            return obj.from_shop == user.shop or obj.to_shop == user.shop
        if user.is_magasinier:
            # Peut gérer uniquement les transferts warehouse de sa boutique
            return obj.transfer_type == 'warehouse' and obj.from_shop == user.shop
        return False
