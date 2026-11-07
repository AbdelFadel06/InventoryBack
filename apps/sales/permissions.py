from rest_framework import permissions

from apps.sales.models.sale import CashierSession


def is_active_cashier(user, shop):
    """L'utilisateur est l'employé désigné caissier de la session active de cette boutique."""
    if user.role != 'EMPLOYEE' or shop is None:
        return False
    session = CashierSession.active_for_shop(shop)
    return session is not None and session.cashier_id == user.id


class IsManagerOrAdmin(permissions.BasePermission):
    """Uniquement Manager et Super Admin"""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_super_admin or request.user.is_shop_manager


class NoWarehouseAccess(permissions.BasePermission):
    """Le magasinier n'a pas accès à la caisse, même en lecture."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and not request.user.is_magasinier)


class CanReadBoutiqueFigures(permissions.BasePermission):
    """Rapports, sessions et dépenses : ni le magasinier, ni le livreur."""
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not user.is_magasinier and user.role != 'LIVREUR')


class IsRegisterOperator(permissions.BasePermission):
    """Vente, dépense, argent d'un livreur : manager ou caissier de la session active."""
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_shop_manager or is_active_cashier(user, view.get_active_shop(request))


class CanModifyDelivery(permissions.BasePermission):
    """
    Manager et Super Admin : à tout moment.
    Caissier de la session active : tant que la livraison n'est ni collectée ni payée.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return (
            user.is_super_admin
            or user.is_shop_manager
            or is_active_cashier(user, view.get_active_shop(request))
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_super_admin or user.is_shop_manager:
            return True
        return obj.delivered_at is None and obj.payment_status == 'pending'


class IsLivreur(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'LIVREUR')
