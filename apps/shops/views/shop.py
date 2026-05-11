from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone

from apps.shops.models import Shop, ShopAssignment
from apps.shops.serializers import (
    ShopSerializer,
    ShopCreateSerializer,
    ShopUpdateSerializer,
    ShopListSerializer,
    ShopDetailSerializer,
    ShopAssignmentSerializer,
    ShopAssignEmployeesSerializer,
)
from apps.shops.permissions import IsSuperAdminOrReadOnly, CanManageShop
from apps.accounts.permissions import IsSuperAdmin


class ShopViewSet(viewsets.ModelViewSet):
    queryset = Shop.objects.prefetch_related('managers').select_related('created_by').all()
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

        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        user = self.request.user

        if user.is_super_admin:
            return queryset

        # Manager voit ses boutiques (toutes celles qu'il gère)
        if user.is_shop_manager:
            return queryset.filter(managers=user)

        # Employee voit uniquement sa boutique courante
        if user.shop:
            return queryset.filter(id=user.shop.id)

        return queryset.none()

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageShop()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def employees(self, request, pk=None):
        """Liste des employés actuellement affectés à la boutique."""
        shop = self.get_object()

        if not request.user.is_super_admin and request.user.shop_id != shop.id:
            if not shop.managers.filter(id=request.user.id).exists():
                return Response({'error': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)

        from apps.accounts.serializers import UserListSerializer
        employees = shop.get_employees()
        return Response({
            'shop': shop.name,
            'total_employees': employees.count(),
            'employees': UserListSerializer(employees, many=True).data
        })

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def staff(self, request, pk=None):
        """Tous les membres du personnel (managers + employés)."""
        shop = self.get_object()

        if not request.user.is_super_admin and request.user.shop_id != shop.id:
            if not shop.managers.filter(id=request.user.id).exists():
                return Response({'error': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)

        from apps.accounts.serializers import UserListSerializer
        staff = shop.get_all_staff()
        return Response({
            'shop': shop.name,
            'total_staff': staff.count(),
            'managers': UserListSerializer(shop.managers.all(), many=True).data,
            'employees': UserListSerializer(staff, many=True).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def assign_manager(self, request, pk=None):
        """
        Ajouter ou retirer un manager de la boutique.
        POST /api/shops/{id}/assign_manager/
        Body: { "manager_id": 5, "action": "add" | "remove" }
        """
        shop = self.get_object()
        if not request.user.is_super_admin:
            return Response({'error': 'Réservé au Super Admin.'}, status=status.HTTP_403_FORBIDDEN)

        manager_id = request.data.get('manager_id')
        action_type = request.data.get('action', 'add')

        if not manager_id:
            return Response({'error': 'manager_id est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.accounts.models import User
        try:
            manager = User.objects.get(id=manager_id)
        except User.DoesNotExist:
            return Response({'error': 'Manager introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        if manager.role != 'SHOP_MANAGER':
            return Response({'error': 'Cet utilisateur n\'est pas un manager.'}, status=status.HTTP_400_BAD_REQUEST)

        if action_type == 'add':
            shop.managers.add(manager)
            if not manager.shop:
                manager.shop = shop
                manager.save(update_fields=['shop'])
            msg = f'{manager.get_full_name()} ajouté comme manager de "{shop.name}".'
        else:
            shop.managers.remove(manager)
            msg = f'{manager.get_full_name()} retiré des managers de "{shop.name}".'

        return Response({'message': msg, 'shop': ShopSerializer(shop).data})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def assign_employees(self, request, pk=None):
        """
        Affecter des employés à la boutique (avec historique).
        POST /api/shops/{id}/assign_employees/
        Body: { "user_ids": [1, 2, 3], "start_date": "2026-04-10", "note": "..." }
        """
        shop = self.get_object()
        is_manager_of_shop = shop.managers.filter(id=request.user.id).exists()
        if not request.user.is_super_admin and not is_manager_of_shop:
            return Response({'error': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ShopAssignEmployeesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = serializer.validated_data['user_ids']
        start_date = serializer.validated_data.get('start_date', timezone.now().date())
        note = serializer.validated_data.get('note', '')

        from apps.accounts.models import User

        # Le manager ne peut affecter que des employés dont il gère la home_shop
        if request.user.is_shop_manager:
            managed_shop_ids = request.user.managed_shops.values_list('id', flat=True)
            users = User.objects.filter(id__in=user_ids, home_shop_id__in=managed_shop_ids)
        else:
            users = User.objects.filter(id__in=user_ids)

        assigned = []

        for user in users:
            # Fermer l'affectation active précédente si différente boutique
            ShopAssignment.objects.filter(user=user, is_active=True).exclude(shop=shop).update(
                is_active=False,
                end_date=start_date
            )
            # Créer la nouvelle affectation si elle n'existe pas déjà
            assignment, created = ShopAssignment.objects.get_or_create(
                user=user, shop=shop, is_active=True,
                defaults={'start_date': start_date, 'assigned_by': request.user, 'note': note}
            )
            # Mettre à jour la boutique courante de l'employé
            user.shop = shop
            user.save(update_fields=['shop'])
            assigned.append(user.get_full_name())

        return Response({
            'message': f'{len(assigned)} employé(s) affecté(s) à "{shop.name}".',
            'assigned': assigned
        })

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def assignment_history(self, request, pk=None):
        """
        Historique des affectations de la boutique.
        GET /api/shops/{id}/assignment_history/
        """
        shop = self.get_object()
        is_manager_of_shop = shop.managers.filter(id=request.user.id).exists()
        if not request.user.is_super_admin and not is_manager_of_shop:
            return Response({'error': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)

        assignments = ShopAssignment.objects.filter(shop=shop).select_related('user', 'assigned_by')
        return Response(ShopAssignmentSerializer(assignments, many=True).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def toggle_active(self, request, pk=None):
        """Activer/Désactiver une boutique."""
        if not request.user.is_super_admin:
            return Response({'error': 'Réservé au Super Admin.'}, status=status.HTTP_403_FORBIDDEN)
        shop = self.get_object()
        shop.is_active = not shop.is_active
        shop.save()
        return Response({
            'message': f'Boutique "{shop.name}" {"activée" if shop.is_active else "désactivée"}.',
            'is_active': shop.is_active
        })

    @action(detail=False, methods=['get'], permission_classes=[IsSuperAdmin])
    def statistics(self, request):
        """Statistiques globales des boutiques."""
        total_shops = Shop.objects.count()
        active_shops = Shop.objects.filter(is_active=True).count()
        top_shops = Shop.objects.annotate(
            employee_count=Count('users', filter=Q(users__is_active=True))
        ).order_by('-employee_count')[:5]

        return Response({
            'total_shops': total_shops,
            'active_shops': active_shops,
            'inactive_shops': total_shops - active_shops,
            'top_shops_by_employees': ShopListSerializer(top_shops, many=True).data
        })
