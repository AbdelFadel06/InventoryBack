from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q

from apps.shops.models import Shop
from apps.shops.serializers import (
    ShopSerializer,
    ShopCreateSerializer,
    ShopUpdateSerializer,
    ShopListSerializer,
    ShopDetailSerializer
)
from apps.shops.permissions import IsSuperAdminOrReadOnly, CanManageShop
from apps.accounts.permissions import IsSuperAdmin


class ShopViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les boutiques

    Permissions:
    - list/retrieve: Tous les utilisateurs authentifiés
    - create/update/delete: Super Admin uniquement
    - Managers peuvent voir leur boutique en détail
    """
    queryset = Shop.objects.select_related('manager', 'created_by').all()
    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action == 'create':
            return ShopCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ShopUpdateSerializer
        elif self.action == 'list':
            return ShopListSerializer
        elif self.action == 'retrieve':
            return ShopDetailSerializer
        return ShopSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Pour la génération du schéma Swagger
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        user = self.request.user

        # Super Admin voit toutes les boutiques
        if user.is_super_admin:
            return queryset

        # Shop Manager voit uniquement sa boutique
        if user.is_shop_manager:
            if user.shop:
                return queryset.filter(id=user.shop.id)
            return queryset.none()

        # Employee voit uniquement sa boutique
        if user.is_employee:
            if user.shop:
                return queryset.filter(id=user.shop.id)
            return queryset.none()

        return queryset.none()

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageShop()]
        return super().get_permissions()

    def perform_create(self, serializer):
        """Créer une boutique et assigner le créateur"""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def employees(self, request, pk=None):
        """
        Liste des employés d'une boutique
        GET /api/shops/{id}/employees/
        """
        shop = self.get_object()

        # Vérifier les permissions
        if not request.user.is_super_admin:
            if request.user.shop != shop:
                return Response(
                    {'error': 'Vous ne pouvez pas voir les employés de cette boutique.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        from apps.accounts.serializers import UserListSerializer
        employees = shop.get_employees()
        serializer = UserListSerializer(employees, many=True)

        return Response({
            'shop': shop.name,
            'total_employees': employees.count(),
            'employees': serializer.data
        })

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def staff(self, request, pk=None):
        """
        Tous les membres du personnel (manager + employés)
        GET /api/shops/{id}/staff/
        """
        shop = self.get_object()

        # Vérifier les permissions
        if not request.user.is_super_admin:
            if request.user.shop != shop:
                return Response(
                    {'error': 'Vous ne pouvez pas voir le personnel de cette boutique.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        from apps.accounts.serializers import UserListSerializer
        staff = shop.get_all_staff()
        serializer = UserListSerializer(staff, many=True)

        return Response({
            'shop': shop.name,
            'total_staff': staff.count(),
            'manager': UserListSerializer(shop.manager).data if shop.manager else None,
            'employees': serializer.data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def assign_manager(self, request, pk=None):
        """
        Assigner un manager à une boutique
        POST /api/shops/{id}/assign_manager/

        Body:
        {
            "manager_id": 5
        }
        """
        shop = self.get_object()
        manager_id = request.data.get('manager_id')

        if not manager_id:
            return Response(
                {'error': 'manager_id est requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from apps.accounts.models import User
            new_manager = User.objects.get(id=manager_id)

            # Vérifier que c'est bien un manager
            if new_manager.role != 'SHOP_MANAGER':
                return Response(
                    {'error': 'Cet utilisateur n\'est pas un manager.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Vérifier qu'il n'est pas déjà assigné à une autre boutique
            if hasattr(new_manager, 'managed_shop') and new_manager.managed_shop:
                if new_manager.managed_shop.id != shop.id:
                    return Response(
                        {'error': f'{new_manager.get_full_name()} gère déjà la boutique "{new_manager.managed_shop.name}".'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Retirer l'ancien manager
            old_manager = shop.manager
            if old_manager:
                old_manager.shop = None
                old_manager.save()

            # Assigner le nouveau manager
            shop.manager = new_manager
            shop.save()

            new_manager.shop = shop
            new_manager.save()

            return Response({
                'message': f'{new_manager.get_full_name()} est maintenant le manager de "{shop.name}".',
                'shop': ShopSerializer(shop).data
            })

        except User.DoesNotExist:
            return Response(
                {'error': 'Manager introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def toggle_active(self, request, pk=None):
        """
        Activer/Désactiver une boutique
        POST /api/shops/{id}/toggle_active/
        """
        shop = self.get_object()
        shop.is_active = not shop.is_active
        shop.save()

        return Response({
            'message': f'Boutique "{shop.name}" {"activée" if shop.is_active else "désactivée"} avec succès.',
            'is_active': shop.is_active
        })

    @action(detail=False, methods=['get'], permission_classes=[IsSuperAdmin])
    def statistics(self, request):
        """
        Statistiques globales des boutiques (Super Admin only)
        GET /api/shops/statistics/
        """
        total_shops = Shop.objects.count()
        active_shops = Shop.objects.filter(is_active=True).count()
        inactive_shops = total_shops - active_shops
        shops_with_manager = Shop.objects.filter(manager__isnull=False).count()
        shops_without_manager = total_shops - shops_with_manager

        # Boutiques avec le plus d'employés
        top_shops = Shop.objects.annotate(
            employee_count=Count('users', filter=Q(users__is_active=True))
        ).order_by('-employee_count')[:5]

        from apps.shops.serializers import ShopListSerializer

        return Response({
            'total_shops': total_shops,
            'active_shops': active_shops,
            'inactive_shops': inactive_shops,
            'shops_with_manager': shops_with_manager,
            'shops_without_manager': shops_without_manager,
            'top_shops_by_employees': ShopListSerializer(top_shops, many=True).data
        })
