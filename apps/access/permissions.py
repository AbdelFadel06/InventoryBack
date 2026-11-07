from rest_framework.permissions import BasePermission

from .services import gate_view


class GridGate(BasePermission):
    """
    Pour les actions que l'ancien code ouvrait à tout compte connecté : sans effet tant que
    l'interrupteur du module est éteint, la grille décide quand il est allumé.
    """

    def has_permission(self, request, view):
        return gate_view(request, view, True)
