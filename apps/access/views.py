"""
Écran des permissions, réservé au Super Admin.

GET  /api/access/catalog/          → modules, droits, colonnes, rôles
GET  /api/access/roles/            → grille rôle × droit
PUT  /api/access/roles/            → {role, code, allowed}            (une case)
GET  /api/access/users/<id>/       → droits effectifs d'une personne et ses exceptions
PUT  /api/access/users/<id>/       → {code, allowed: true|false|null} (null : retour à la règle du rôle)
GET  /api/access/switches/         → interrupteurs par module + arrêt d'urgence
PUT  /api/access/switches/         → {module, enabled}
GET  /api/access/history/          → 100 derniers changements
Chaque modification est inscrite au journal (PermissionChange).
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .catalog import ADMIN, BY_CODE, MANAGE_PERMISSIONS, PERMISSIONS, ROLES
from .models import ModuleSwitch, PermissionChange, RolePermission, UserPermission
from .services import (
    SWITCHES, emergency_stop, effective_permissions, enabled_modules, forget_switches, has_perm,
)

SWITCH_PREFIX = 'interrupteur:'
SWITCH_LABELS = {
    'comptes': 'Comptes', 'boutiques': 'Boutiques', 'produits': 'Produits',
    'stock': 'Stock et transferts', 'inventaires': 'Inventaires', 'ventes': 'Caisse, ventes et livraisons',
}


class CanManagePermissions(BasePermission):
    message = "Réservé au Super Admin."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == ADMIN
                    and has_perm(request.user, MANAGE_PERMISSIONS))


def _bad(message):
    return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


def _locked(role, code):
    """Le Super Admin garde toujours « Gérer les permissions »."""
    return role == ADMIN and code == MANAGE_PERMISSIONS


class AccessView(APIView):
    permission_classes = [IsAuthenticated, CanManagePermissions]


class CatalogView(AccessView):

    def get(self, request):
        return Response({
            'roles': list(ROLES),
            'permissions': [
                {'code': p.code, 'module': p.module, 'label': p.label, 'kind': p.kind,
                 'locked_for': [ADMIN] if p.code == MANAGE_PERMISSIONS else []}
                for p in PERMISSIONS
            ],
        })


class RoleGridView(AccessView):

    def get(self, request):
        grid = {role: {} for role in ROLES}
        for role, code, allowed in RolePermission.objects.values_list('role', 'code', 'allowed'):
            if role in grid:
                grid[role][code] = allowed
        return Response(grid)

    def put(self, request):
        role, code, allowed = request.data.get('role'), request.data.get('code'), request.data.get('allowed')
        if role not in ROLES or code not in BY_CODE or not isinstance(allowed, bool):
            return _bad("Rôle, droit ou valeur invalide.")
        if _locked(role, code):
            return _bad("Le Super Admin garde toujours ce droit.")
        with transaction.atomic():
            row = RolePermission.objects.select_for_update().filter(role=role, code=code).first()
            before = row.allowed if row else None
            if row is None:
                RolePermission.objects.create(role=role, code=code, allowed=allowed)
            elif row.allowed != allowed:
                row.allowed = allowed
                row.save(update_fields=['allowed', 'updated_at'])
            if before != allowed:
                PermissionChange.objects.create(
                    changed_by=request.user, role=role, code=code, before=before, after=allowed)
        return Response({'role': role, 'code': code, 'allowed': allowed})


class UserPermissionsView(AccessView):

    def payload(self, user):
        return {
            'user': user.id,
            'name': user.get_full_name() or user.email,
            'role': user.role,
            'effective': effective_permissions(user),
            'overrides': dict(UserPermission.objects.filter(user=user).values_list('code', 'allowed')),
        }

    def get(self, request, user_id):
        return Response(self.payload(get_object_or_404(User, id=user_id)))

    def put(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        code, allowed = request.data.get('code'), request.data.get('allowed')
        if code not in BY_CODE or allowed not in (True, False, None):
            return _bad("Droit ou valeur invalide.")
        if _locked(user.role, code):
            return _bad("Le Super Admin garde toujours ce droit.")
        with transaction.atomic():
            existing = UserPermission.objects.select_for_update().filter(user=user, code=code).first()
            before = existing.allowed if existing else None
            if allowed is None:
                if existing:
                    existing.delete()
            elif existing:
                existing.allowed = allowed
                existing.save(update_fields=['allowed', 'updated_at'])
            else:
                UserPermission.objects.create(user=user, code=code, allowed=allowed)
            if before != allowed:
                PermissionChange.objects.create(
                    changed_by=request.user, user=user, code=code, before=before, after=allowed)
        fresh = User.objects.get(id=user.id)   # droits recalculés, sans cache
        return Response(self.payload(fresh))


class SwitchesView(AccessView):

    def payload(self):
        on = enabled_modules()
        from_screen = set(ModuleSwitch.objects.filter(enabled=True).values_list('module', flat=True))
        return {
            'emergency_stop': emergency_stop(),
            'modules': [
                {'module': m, 'label': SWITCH_LABELS.get(m, m), 'enabled': m in from_screen,
                 'effective': 'all' in on or m in on}
                for m in SWITCHES
            ],
        }

    def get(self, request):
        return Response(self.payload())

    def put(self, request):
        module, enabled = request.data.get('module'), request.data.get('enabled')
        if module not in SWITCHES or not isinstance(enabled, bool):
            return _bad("Module ou valeur invalide.")
        with transaction.atomic():
            switch, created = ModuleSwitch.objects.select_for_update().get_or_create(module=module)
            before = None if created else switch.enabled
            if switch.enabled != enabled or created:
                switch.enabled = enabled
                switch.updated_by = request.user
                switch.save()
                PermissionChange.objects.create(
                    changed_by=request.user, code=f'{SWITCH_PREFIX}{module}', before=before, after=enabled)
        forget_switches()
        return Response(self.payload())


class HistoryView(AccessView):

    def get(self, request):
        rows = PermissionChange.objects.select_related('changed_by', 'user')[:100]
        labels = {p.code: p.label for p in PERMISSIONS}
        return Response([
            {
                'id': row.id,
                'at': row.created_at,
                'by': (row.changed_by.get_full_name() or row.changed_by.email) if row.changed_by else None,
                'role': row.role or None,
                'user': (row.user.get_full_name() or row.user.email) if row.user else None,
                'code': row.code,
                'label': (f"Interrupteur « {SWITCH_LABELS.get(row.code[len(SWITCH_PREFIX):], row.code)} »"
                          if row.code.startswith(SWITCH_PREFIX) else labels.get(row.code, row.code)),
                'before': row.before,
                'after': row.after,
            }
            for row in rows
        ])
