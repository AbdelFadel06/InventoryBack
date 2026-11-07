from rest_framework import permissions

from apps.access.services import gate, gate_view, view_code


class IsSuperAdminOrReadOnly(permissions.BasePermission):
    """
    Permission: Seul le Super Admin peut créer/modifier/supprimer
    Les autres peuvent uniquement lire
    """
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Lecture autorisée pour tous les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return gate_view(request, view, True)

        # Création/modification/suppression: Super Admin uniquement
        return gate_view(request, view, user.is_super_admin)


class CanManageShop(permissions.BasePermission):
    """
    Permission pour gérer une boutique:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut gérer uniquement sa propre boutique
    """
    def has_object_permission(self, request, view, obj):
        user = request.user
        code = view_code(view, request)

        # Super Admin peut tout faire
        if user.is_super_admin:
            return gate(user, code, True) if code else True

        # Shop Manager peut gérer sa propre boutique (lecture seule)
        if user.is_shop_manager:
            # Le manager peut voir sa boutique
            if view.action == 'retrieve':
                return obj == user.shop
            # Il ne peut pas la modifier/supprimer, sauf si la grille le lui donne (et seulement les siennes).
            if code:
                return gate(user, code, False) and user.managed_shops.filter(id=obj.id).exists()
            return False

        return False
