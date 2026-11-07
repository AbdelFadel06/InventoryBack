from rest_framework import permissions

from apps.access.services import gate, gate_view, view_code


class CanManageProducts(permissions.BasePermission):
    """
    Permission pour gérer les produits:
    - SUPER_ADMIN: peut tout gérer (tous les produits)
    - SHOP_MANAGER: peut gérer les produits de sa boutique uniquement
    - EMPLOYEE: lecture seule des produits de sa boutique
    La partie « rôle » passe par l'aiguillage (ancienne règle ou grille) ; la boutique reste vérifiée ici.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Tout le monde authentifié peut lire
        if request.method in permissions.SAFE_METHODS:
            return gate_view(request, view, True)

        # Création/modification/suppression: Super Admin ou Shop Manager
        return gate_view(request, view, user.is_super_admin or user.is_shop_manager)

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

        # Autre rôle à qui la grille donne ce droit : produits de sa boutique seulement.
        code = view_code(view, request)
        return bool(code) and gate(user, code, False) and obj.shop_id == user.shop_id


class CanManageCategories(permissions.BasePermission):
    """
    Permission pour gérer les catégories:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut créer/modifier des catégories
    - EMPLOYEE: lecture seule
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Lecture pour tout le monde authentifié
        if request.method in permissions.SAFE_METHODS:
            return gate_view(request, view, True)

        # Création/modification: Super Admin ou Shop Manager
        return gate_view(request, view, user.is_super_admin or user.is_shop_manager)
