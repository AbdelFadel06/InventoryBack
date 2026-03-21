from rest_framework import permissions


class IsSuperAdminOrReadOnly(permissions.BasePermission):
    """
    Permission: Seul le Super Admin peut créer/modifier/supprimer
    Les autres peuvent uniquement lire
    """
    def has_permission(self, request, view):
        # Lecture autorisée pour tous les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Création/modification/suppression: Super Admin uniquement
        return request.user and request.user.is_authenticated and request.user.is_super_admin


class CanManageShop(permissions.BasePermission):
    """
    Permission pour gérer une boutique:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut gérer uniquement sa propre boutique
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        # Super Admin peut tout faire
        if user.is_super_admin:
            return True

        # Shop Manager peut gérer sa propre boutique (lecture seule)
        if user.is_shop_manager:
            # Le manager peut voir sa boutique
            if view.action == 'retrieve':
                return obj == user.shop
            # Mais ne peut pas la modifier/supprimer
            return False

        return False
