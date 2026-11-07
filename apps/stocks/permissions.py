from rest_framework import permissions

from apps.access.services import gate_view


def manages_shop(user, shop):
    """Boutique courante du manager, ou l'une de celles qu'il gère (multi-boutiques)."""
    return user.shop_id == shop.id or user.managed_shops.filter(id=shop.id).exists()


class CanWriteStock(permissions.BasePermission):
    """Entrées et sorties de stock : Super Admin, Manager et Magasinier."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return gate_view(request, view, user.is_super_admin or user.is_shop_manager or user.is_magasinier)


class CanManageStock(permissions.BasePermission):
    """
    - SUPER_ADMIN   : tout
    - SHOP_MANAGER  : stocks de sa boutique (lecture + écriture)
    - MAGASINIER    : stocks de sa boutique (lecture + écriture stock MAGASIN uniquement)
    - EMPLOYEE/LIVREUR : lecture seule
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return gate_view(request, view, True)
        return gate_view(request, view, user.is_super_admin or user.is_shop_manager or user.is_magasinier)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in permissions.SAFE_METHODS:
            if user.is_super_admin:
                return True
            if user.is_shop_manager:
                return manages_shop(user, obj.shop)
            return obj.shop == user.shop

        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            return manages_shop(user, obj.shop)
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
        user = request.user
        return bool(user and user.is_authenticated) and gate_view(request, view, True)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            return manages_shop(user, obj.shop)
        return obj.shop == user.shop


class CanManageTransfers(permissions.BasePermission):
    """
    - SUPER_ADMIN  : tout
    - SHOP_MANAGER : créer, envoyer, recevoir les transferts de/vers sa boutique
    - MAGASINIER   : créer et envoyer les transferts warehouse→boutique de sa boutique
    - EMPLOYEE     : lecture seule
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return gate_view(request, view, True)
        return gate_view(request, view, user.is_super_admin or user.is_shop_manager or user.is_magasinier)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in permissions.SAFE_METHODS:
            if user.is_super_admin:
                return True
            if user.is_shop_manager:
                return manages_shop(user, obj.from_shop) or manages_shop(user, obj.to_shop)
            return obj.from_shop == user.shop or obj.to_shop == user.shop

        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            return manages_shop(user, obj.from_shop) or manages_shop(user, obj.to_shop)
        if user.is_magasinier:
            # Peut gérer uniquement les transferts warehouse de sa boutique
            return obj.transfer_type == 'warehouse' and obj.from_shop == user.shop
        return False
