from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q

from apps.accounts.models import User
from apps.accounts.serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    UserListSerializer
)
from apps.accounts.permissions import (
    IsSuperAdmin,
    IsShopManagerOrSuperAdmin,
    CanManageUser
)
from apps.shops.models import Shop


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les utilisateurs

    Permissions:
    - list/retrieve: Super Admin ou Shop Manager (voit que sa boutique)
    - create: Super Admin ou Shop Manager
    - update/delete: CanManageUser permission
    """
    queryset = User.objects.select_related('shop').all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        elif self.action == 'list':
            return UserListSerializer
        elif self.action == 'change_password':
            return ChangePasswordSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsShopManagerOrSuperAdmin()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        if user.is_super_admin:
            return queryset

        # Manager voit les employés dont home_shop est dans ses boutiques gérées
        if user.is_shop_manager:
            managed_shop_ids = user.managed_shops.values_list('id', flat=True)
            return queryset.filter(home_shop_id__in=managed_shop_ids)

        return queryset.filter(id=user.id)

    def perform_create(self, serializer):
        user = self.request.user

        if user.is_shop_manager:
            role = serializer.validated_data.get('role', 'EMPLOYEE')
            if role not in ('EMPLOYEE', 'LIVREUR', 'MAGASINIER'):
                role = 'EMPLOYEE'
            # Utilise la boutique active (X-Active-Shop header) si disponible
            home_shop = None
            active_shop_id = self.request.headers.get('X-Active-Shop')
            if active_shop_id:
                try:
                    home_shop = user.managed_shops.get(id=int(active_shop_id))
                except (ValueError, Shop.DoesNotExist):
                    pass
            if not home_shop:
                home_shop = user.managed_shops.first()
            serializer.save(role=role, shop=home_shop, home_shop=home_shop)
        else:
            serializer.save()

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Récupérer le profil de l'utilisateur connecté
        GET /api/users/me/
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['put', 'patch'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """
        Mettre à jour son propre profil
        PUT/PATCH /api/users/update_profile/
        """
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=request.method == 'PATCH'
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        Changer son mot de passe
        POST /api/users/change_password/
        """
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            'message': 'Mot de passe modifié avec succès.'
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[IsSuperAdmin])
    def managers(self, request):
        """
        Liste des managers de boutique (Super Admin only)
        GET /api/users/managers/
        """
        managers = self.get_queryset().filter(role='SHOP_MANAGER')
        serializer = UserListSerializer(managers, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsShopManagerOrSuperAdmin])
    def employees(self, request):
        """
        Liste des employés et livreurs.
        ?shop=<id>       → filtre par boutique courante (user.shop, affectation active)
        ?home_shop=<id>  → filtre par boutique d'appartenance permanente (user.home_shop)
        Sans paramètre   → tout le pool (toutes boutiques gérées)
        """
        user = request.user
        queryset = self.get_queryset().filter(role__in=['EMPLOYEE', 'MAGASINIER'])

        def _validate_shop_id(raw_id):
            """Retourne l'entier si le manager gère cette boutique, sinon None."""
            try:
                sid = int(raw_id)
            except (ValueError, TypeError):
                return None
            if user.is_super_admin:
                return sid
            if user.is_shop_manager and user.managed_shops.filter(id=sid).exists():
                return sid
            return None

        # Filtre par affectation courante
        shop_param = request.query_params.get('shop')
        if shop_param:
            sid = _validate_shop_id(shop_param)
            if sid:
                queryset = queryset.filter(shop_id=sid)

        # Filtre par boutique d'appartenance permanente
        home_shop_param = request.query_params.get('home_shop')
        if home_shop_param:
            sid = _validate_shop_id(home_shop_param)
            if sid:
                queryset = queryset.filter(home_shop_id=sid)

        serializer = UserListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def livreurs(self, request):
        """
        Liste des livreurs — filtrés par home_shop du manager (ou shop actif).
        Les livreurs peuvent travailler pour plusieurs boutiques mais sont
        visibles uniquement aux managers de la boutique qui les a créés.
        GET /api/users/livreurs/
        """
        user = request.user
        queryset = User.objects.filter(role='LIVREUR', is_active=True)

        if user.is_super_admin:
            shop_id = request.query_params.get('shop')
            if shop_id:
                queryset = queryset.filter(home_shop_id=shop_id)
        elif user.is_shop_manager:
            # Livreurs dont home_shop est parmi les boutiques gérées
            managed_shop_ids = user.managed_shops.values_list('id', flat=True)
            queryset = queryset.filter(home_shop_id__in=managed_shop_ids)
        else:
            # Employé/caissier — livreurs de sa boutique courante
            if user.shop:
                queryset = queryset.filter(home_shop=user.shop)
            else:
                queryset = queryset.none()

        serializer = UserListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsShopManagerOrSuperAdmin])
    def toggle_active(self, request, pk=None):
        """
        Activer/Désactiver un utilisateur
        POST /api/users/{id}/toggle_active/
        """
        user_to_toggle = self.get_object()

        # Vérifier les permissions
        if not self.request.user.is_super_admin:
            if user_to_toggle.shop != self.request.user.shop:
                return Response(
                    {'error': 'Vous ne pouvez pas modifier cet utilisateur.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        user_to_toggle.is_active = not user_to_toggle.is_active
        user_to_toggle.save()

        return Response({
            'message': f'Utilisateur {"activé" if user_to_toggle.is_active else "désactivé"} avec succès.',
            'is_active': user_to_toggle.is_active
        })
