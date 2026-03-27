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

        # Super Admin voit tous les utilisateurs
        if user.is_super_admin:
            return queryset

        # Shop Manager voit que les utilisateurs de sa boutique
        if user.is_shop_manager:
            return queryset.filter(shop=user.shop)

        # Employee voit que son propre profil
        return queryset.filter(id=user.id)

    def perform_create(self, serializer):
        """
        Création d'utilisateur avec logique métier
        """
        user = self.request.user

        # Shop Manager peut créer des employés et des livreurs pour sa boutique
        if user.is_shop_manager:
            role = serializer.validated_data.get('role', 'EMPLOYEE')
            if role not in ('EMPLOYEE', 'LIVREUR'):
                role = 'EMPLOYEE'
            serializer.save(role=role, shop=user.shop)
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
        Liste des employés et livreurs
        GET /api/users/employees/
        """
        queryset = self.get_queryset().filter(role__in=['EMPLOYEE', 'LIVREUR'])

        # Filtre optionnel par boutique (pour Super Admin)
        shop_id = request.query_params.get('shop')
        if shop_id and request.user.is_super_admin:
            queryset = queryset.filter(shop_id=shop_id)

        serializer = UserListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def livreurs(self, request):
        """
        Liste des livreurs uniquement — accessible à tous les utilisateurs connectés
        (les caissiers en ont besoin pour les livraisons en POS)
        GET /api/users/livreurs/
        """
        queryset = User.objects.filter(role='LIVREUR', is_active=True)

        if request.user.is_super_admin:
            shop_id = request.query_params.get('shop')
            if shop_id:
                queryset = queryset.filter(shop_id=shop_id)
        else:
            # Filtre par boutique de l'utilisateur connecté
            queryset = queryset.filter(shop=request.user.shop)

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
