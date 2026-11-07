from rest_framework import permissions

from apps.access.services import gate, gate_view, view_code


class CanManageInventories(permissions.BasePermission):
    """
    Permission pour gérer les inventaires:
    - SUPER_ADMIN: peut tout gérer
    - SHOP_MANAGER: peut gérer les inventaires de sa boutique
    - EMPLOYEE: peut compter les produits de sa boutique
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Tout le monde authentifié peut lire
        if request.method in permissions.SAFE_METHODS:
            return gate_view(request, view, True)

        # Création: Super Admin ou Shop Manager
        if view.action == 'create':
            return gate_view(request, view, user.is_super_admin or user.is_shop_manager)

        # Autres actions : décidées sur l'inventaire lui-même (has_object_permission)
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        code = view_code(view, request)

        def role_ok(legacy):
            return gate(user, code, legacy) if code else legacy

        if user.is_super_admin:
            return role_ok(True)

        if user.is_shop_manager:
            return user.managed_shops.filter(id=obj.shop_id).exists() and role_ok(True)

        # Autres rôles : lecture + comptage sur leur boutique. Annuler, supprimer
        # ou faire avancer un inventaire est réservé au manager et au Super Admin.
        if view.action in ['count_product', 'count_multiple'] or request.method in permissions.SAFE_METHODS:
            return obj.shop == user.shop and role_ok(True)
        return role_ok(False) and obj.shop == user.shop


class CanCountInventory(permissions.BasePermission):
    """
    Permission pour compter les produits:
    - Tous les employés de la boutique peuvent compter
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated) and gate_view(request, view, True)

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_super_admin:
            return True

        if user.is_shop_manager:
            return user.managed_shops.filter(id=obj.shop_id).exists()

        return obj.shop == user.shop


class CanValidateInventory(permissions.BasePermission):
    """
    Permission pour valider un inventaire:
    - SUPER_ADMIN: peut valider tous les inventaires
    - SHOP_MANAGER: peut valider les inventaires de sa boutique
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated) and gate_view(
            request, view, user.is_super_admin or user.is_shop_manager)

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_super_admin:
            return True

        if user.is_shop_manager:
            return user.managed_shops.filter(id=obj.shop_id).exists()

        # Autre rôle à qui la grille donne ce droit : inventaires de sa boutique seulement.
        code = view_code(view, request)
        return bool(code) and gate(user, code, False) and obj.shop == user.shop
