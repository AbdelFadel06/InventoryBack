"""
Lecture des permissions, réservée au Super Admin (l'écran de modification viendra à l'étape 6).

GET /api/access/catalog/         → modules, droits, colonnes
GET /api/access/roles/           → grille rôle × droit
GET /api/access/users/<id>/      → droits effectifs d'une personne et ses exceptions
"""
from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .catalog import MANAGE_PERMISSIONS, PERMISSIONS, ROLES
from .models import RolePermission, UserPermission
from .services import effective_permissions, has_perm


class CanManagePermissions(BasePermission):
    message = "Réservé au Super Admin."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'SUPER_ADMIN'
                    and has_perm(request.user, MANAGE_PERMISSIONS))


class CatalogView(APIView):
    permission_classes = [IsAuthenticated, CanManagePermissions]

    def get(self, request):
        return Response({
            'roles': list(ROLES),
            'permissions': [
                {'code': p.code, 'module': p.module, 'label': p.label, 'kind': p.kind}
                for p in PERMISSIONS
            ],
        })


class RoleGridView(APIView):
    permission_classes = [IsAuthenticated, CanManagePermissions]

    def get(self, request):
        grid = {role: {} for role in ROLES}
        for role, code, allowed in RolePermission.objects.values_list('role', 'code', 'allowed'):
            if role in grid:
                grid[role][code] = allowed
        return Response(grid)


class UserPermissionsView(APIView):
    permission_classes = [IsAuthenticated, CanManagePermissions]

    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        return Response({
            'user': user.id,
            'role': user.role,
            'effective': effective_permissions(user),
            'overrides': dict(UserPermission.objects.filter(user=user).values_list('code', 'allowed')),
        })
