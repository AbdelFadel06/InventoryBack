from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from apps.inventories.models import Inventory, InventoryLine
from apps.inventories.serializers import (
    InventorySerializer,
    InventoryCreateSerializer,
    InventoryDetailSerializer,
    InventoryListSerializer,
    InventoryLineSerializer,
    InventoryLineCountSerializer,
    InventoryDiscrepancySerializer
)
from apps.inventories.permissions import (
    CanManageInventories,
    CanCountInventory,
    CanValidateInventory
)
from apps.stocks.models import Stock, StockMovement


class InventoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les inventaires

    Workflow:
    1. create() - Créer un inventaire (draft)
    2. add_products() - Ajouter les produits à compter
    3. start() - Démarrer l'inventaire (in_progress)
    4. count_product() - Compter chaque produit
    5. complete() - Terminer le comptage (completed)
    6. validate() - Valider et ajuster les stocks (validated)
    """
    queryset = Inventory.objects.select_related('shop', 'created_by', 'validated_by').prefetch_related('lines').all()
    permission_classes = [IsAuthenticated, CanManageInventories]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['shop', 'status', 'inventory_date']
    search_fields = ['reference', 'notes']
    ordering_fields = ['inventory_date', 'created_at']
    ordering = ['-inventory_date']

    def get_serializer_class(self):
        if self.action == 'create':
            return InventoryCreateSerializer
        elif self.action == 'list':
            return InventoryListSerializer
        elif self.action == 'retrieve':
            return InventoryDetailSerializer
        return InventorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Pour Swagger
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        user = self.request.user

        # Super Admin voit tous les inventaires
        if user.is_super_admin:
            return queryset

        # Les autres voient que les inventaires de leur boutique
        if user.shop:
            return queryset.filter(shop=user.shop)

        return queryset.none()

    @action(detail=True, methods=['post'])
    def add_products(self, request, pk=None):
        """
        Ajouter des produits à l'inventaire
        POST /api/inventories/{id}/add_products/

        Body:
        {
            "product_ids": [1, 2, 3],  // Liste de produits à ajouter
            "add_all": false            // ou true pour ajouter tous les produits de la boutique
        }
        """
        inventory = self.get_object()

        # Vérifier que l'inventaire est en brouillon
        if inventory.status != 'draft':
            return Response(
                {'error': 'Les produits ne peuvent être ajoutés qu\'à un inventaire en brouillon.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Récupérer les produits à ajouter
        add_all = request.data.get('add_all', False)

        if add_all:
          from apps.products.models import Product
          # Produits qui ont du stock OU qui sont liés à cette boutique
          products = Product.objects.filter(
              Q(stocks__shop=inventory.shop) | Q(shop=inventory.shop) | Q(shop__isnull=True),
              is_active=True
          ).distinct()
        else:
            product_ids = request.data.get('product_ids', [])
            if not product_ids:
                return Response(
                    {'error': 'product_ids ou add_all est requis.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            from apps.products.models import Product
            products = Product.objects.filter(id__in=product_ids, is_active=True)

        # Créer les lignes d'inventaire
        lines_created = 0
        for product in products:
            # Vérifier si la ligne n'existe pas déjà
            if not InventoryLine.objects.filter(inventory=inventory, product=product).exists():
                # Récupérer le stock actuel
                stock = Stock.objects.filter(product=product, shop=inventory.shop).first()
                expected_quantity = stock.quantity if stock else 0

                InventoryLine.objects.create(
                    inventory=inventory,
                    product=product,
                    expected_quantity=expected_quantity
                )
                lines_created += 1

        return Response({
            'message': f'{lines_created} produits ajoutés à l\'inventaire.',
            'total_products': inventory.total_products
        })

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """
        Démarrer l'inventaire (passer à in_progress)
        POST /api/inventories/{id}/start/
        """
        inventory = self.get_object()

        if inventory.status != 'draft':
            return Response(
                {'error': 'Seul un inventaire en brouillon peut être démarré.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if inventory.total_products == 0:
            return Response(
                {'error': 'Ajoutez des produits avant de démarrer l\'inventaire.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        inventory.status = 'in_progress'
        inventory.save()

        return Response({
            'message': 'Inventaire démarré.',
            'inventory': InventorySerializer(inventory).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanCountInventory])
    def count_product(self, request, pk=None):
        """
        Compter un produit
        POST /api/inventories/{id}/count_product/

        Body:
        {
            "line_id": 5,
            "counted_quantity": 47,
            "notes": "3 produits endommagés"
        }
        """
        inventory = self.get_object()

        if inventory.status not in ['in_progress', 'draft']:
            return Response(
                {'error': 'Le comptage n\'est possible que pour un inventaire en cours.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = InventoryLineCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        line_id = serializer.validated_data['line_id']
        counted_quantity = serializer.validated_data['counted_quantity']
        notes = serializer.validated_data.get('notes', '')

        try:
            line = inventory.lines.get(id=line_id)
        except InventoryLine.DoesNotExist:
            return Response(
                {'error': 'Ligne d\'inventaire introuvable.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Mettre à jour la ligne
        line.counted_quantity = counted_quantity
        line.counted_by = request.user
        line.counted_at = timezone.now()
        if notes:
            line.notes = notes
        line.save()

        return Response({
            'message': 'Comptage enregistré.',
            'line': InventoryLineSerializer(line).data,
            'progress': inventory.counting_progress
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanCountInventory])
    def count_multiple(self, request, pk=None):
        """
        Compter plusieurs produits en une fois
        POST /api/inventories/{id}/count_multiple/

        Body:
        {
            "counts": [
                {"line_id": 1, "counted_quantity": 50},
                {"line_id": 2, "counted_quantity": 23, "notes": "OK"},
                {"line_id": 3, "counted_quantity": 0, "notes": "Rupture"}
            ]
        }
        """
        inventory = self.get_object()

        if inventory.status not in ['in_progress', 'draft']:
            return Response(
                {'error': 'Le comptage n\'est possible que pour un inventaire en cours.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        counts = request.data.get('counts', [])
        if not counts:
            return Response(
                {'error': 'counts est requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        updated = 0
        for count_data in counts:
            try:
                line = inventory.lines.get(id=count_data['line_id'])
                line.counted_quantity = count_data['counted_quantity']
                line.counted_by = request.user
                line.counted_at = timezone.now()
                if 'notes' in count_data:
                    line.notes = count_data['notes']
                line.save()
                updated += 1
            except (InventoryLine.DoesNotExist, KeyError):
                continue

        return Response({
            'message': f'{updated} produits comptés.',
            'progress': inventory.counting_progress
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Terminer le comptage
        POST /api/inventories/{id}/complete/
        """
        inventory = self.get_object()

        if inventory.status != 'in_progress':
            return Response(
                {'error': 'Seul un inventaire en cours peut être terminé.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier que tous les produits sont comptés
        if inventory.products_counted < inventory.total_products:
            return Response(
                {
                    'error': 'Tous les produits doivent être comptés avant de terminer.',
                    'counted': inventory.products_counted,
                    'total': inventory.total_products
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        inventory.status = 'completed'
        inventory.completed_at = timezone.now()
        inventory.save()

        return Response({
            'message': 'Inventaire terminé. Il peut maintenant être validé.',
            'inventory': InventorySerializer(inventory).data
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanValidateInventory])
    def validate(self, request, pk=None):
        """
        Valider l'inventaire et ajuster les stocks
        POST /api/inventories/{id}/validate/
        """
        inventory = self.get_object()

        # Vérifier que l'inventaire peut être validé
        can_validate, message = inventory.can_be_validated()
        if not can_validate:
            return Response(
                {'error': message},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ajuster tous les stocks
        adjustments_made = 0
        for line in inventory.lines.all():
            if line.difference != 0:
                # Créer un mouvement d'ajustement
                StockMovement.objects.create(
                    product=line.product,
                    shop=inventory.shop,
                    movement_type='inventory',
                    quantity=line.difference,
                    reference=inventory.reference,
                    reason=f"Ajustement inventaire {inventory.reference}",
                    notes=line.notes,
                    created_by=request.user
                )
                adjustments_made += 1

        # Marquer l'inventaire comme validé
        inventory.status = 'validated'
        inventory.validated_at = timezone.now()
        inventory.validated_by = request.user
        inventory.save()

        return Response({
            'message': f'Inventaire validé. {adjustments_made} ajustements effectués.',
            'inventory': InventorySerializer(inventory).data
        })

    @action(detail=True, methods=['get'])
    def discrepancies(self, request, pk=None):
        """
        Voir uniquement les écarts
        GET /api/inventories/{id}/discrepancies/
        """
        inventory = self.get_object()

        # Filtrer les lignes avec écarts
        lines_with_discrepancies = [
            line for line in inventory.lines.all()
            if line.is_counted and line.difference != 0
        ]

        serializer = InventoryDiscrepancySerializer(lines_with_discrepancies, many=True)

        return Response({
            'inventory': inventory.reference,
            'total_discrepancies': len(lines_with_discrepancies),
            'total_shortage': inventory.total_shortage,
            'total_surplus': inventory.total_surplus,
            'adjustment_value': inventory.adjustment_value,
            'discrepancies': serializer.data
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Annuler un inventaire
        POST /api/inventories/{id}/cancel/
        """
        inventory = self.get_object()

        if inventory.status == 'validated':
            return Response(
                {'error': 'Un inventaire validé ne peut pas être annulé.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        inventory.status = 'cancelled'
        inventory.save()

        return Response({
            'message': 'Inventaire annulé.',
            'inventory': InventorySerializer(inventory).data
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Statistiques sur les inventaires
        GET /api/inventories/statistics/
        """
        queryset = self.get_queryset()

        total = queryset.count()
        by_status = {}
        for status_code, status_label in Inventory.STATUS_CHOICES:
            count = queryset.filter(status=status_code).count()
            by_status[status_code] = {
                'label': status_label,
                'count': count
            }

        return Response({
            'total_inventories': total,
            'by_status': by_status
        })
