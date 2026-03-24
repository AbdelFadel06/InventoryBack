from rest_framework import permissions


class IsCashierOrManager(permissions.BasePermission):
    """
    - Manager/Admin : accès complet
    - Caissier désigné : peut créer des ventes
    - Livreur : voit ses livraisons
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_super_admin or request.user.is_shop_manager:
            return True
        # EMPLOYEE et LIVREUR peuvent créer si session active
        return request.user.shop is not None

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_super_admin:
            return True
        if user.is_shop_manager:
            return obj.shop == user.shop
        if hasattr(obj, 'cashier') and obj.cashier == user:
            return True
        if hasattr(obj, 'livreur') and obj.livreur == user:
            return request.method in permissions.SAFE_METHODS
        return False


class IsManagerOrAdmin(permissions.BasePermission):
    """Uniquement Manager et Super Admin"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_super_admin or request.user.is_shop_manager
