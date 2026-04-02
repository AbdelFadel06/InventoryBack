from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.stocks.models import Stock, StockMovement, StockTransfer
from apps.stocks.serializers import (
    StockSerializer,
    StockListSerializer,
    StockMovementSerializer,
    StockMovementCreateSerializer,
    StockTransferSerializer,
    StockTransferCreateSerializer,
    StockAdjustmentSerializer,
    StockAlertSerializer
)
from apps.stocks.permissions import (
    CanManageStock,
    CanCreateStockMovement,
    CanManageTransfers
)
from apps.accounts.permissions import IsSuperAdmin


class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.select_related('product', 'shop', 'updated_by').all()
    permission_classes = [IsAuthenticated, CanManageStock]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['shop', 'product', 'product__category', 'location']
    search_fields = ['product__name', 'product__sku', 'product__barcode']
    ordering_fields = ['quantity', 'last_updated', 'product__name']
    ordering = ['product__name']

    def get_serializer_class(self):
        if self.action == 'list':
            return StockListSerializer
        return StockSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()
        user = self.request.user
        if user.is_super_admin:
            return queryset
        if user.shop:
            return queryset.filter(shop=user.shop)
        return queryset.none()

    @action(detail=False, methods=['get'])
    def alerts(self, request):
        queryset   = self.get_queryset()
        alert_type = request.query_params.get('type', 'all')
        if alert_type == 'critical':
            stocks = [s for s in queryset if s.stock_status == 'critical']
        elif alert_type == 'low':
            stocks = [s for s in queryset if s.stock_status in ['low', 'critical']]
        elif alert_type == 'out':
            stocks = [s for s in queryset if s.stock_status == 'out_of_stock']
        else:
            stocks = [s for s in queryset if s.stock_status != 'ok']
        serializer = StockAlertSerializer(stocks, many=True)
        return Response({'total': len(stocks), 'alert_type': alert_type, 'stocks': serializer.data})

    @action(detail=False, methods=['post'])
    def adjust(self, request):
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product      = serializer.validated_data['product']
        shop         = serializer.validated_data['shop']
        location     = serializer.validated_data.get('location', 'BOUTIQUE')
        new_quantity = serializer.validated_data['new_quantity']
        reason       = serializer.validated_data['reason']

        if not request.user.is_super_admin:
            if shop != request.user.shop:
                return Response({'error': 'Vous ne pouvez pas ajuster le stock de cette boutique.'}, status=status.HTTP_403_FORBIDDEN)
            # Magasinier ne peut ajuster que le magasin
            if request.user.is_magasinier and location != 'MAGASIN':
                return Response({'error': 'Vous ne pouvez ajuster que le stock magasin.'}, status=status.HTTP_403_FORBIDDEN)

        stock, _ = Stock.objects.get_or_create(product=product, shop=shop, location=location, defaults={'quantity': 0})
        old_quantity = stock.quantity
        difference   = new_quantity - old_quantity
        movement = StockMovement.objects.create(
            product=product, shop=shop, location=location,
            movement_type='adjustment', quantity=difference,
            reason=reason, created_by=request.user,
        )
        stock.refresh_from_db()
        return Response({
            'message': 'Stock ajusté avec succès.',
            'old_quantity': old_quantity,
            'new_quantity': stock.quantity,
            'difference':   difference,
            'movement_id':  movement.id,
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Totaux stock par produit (boutique + magasin) pour une boutique."""
        queryset = self.get_queryset()
        from django.db.models import Sum
        rows = (
            queryset
            .values('product', 'product__name', 'product__sku', 'shop')
            .annotate(
                boutique=Sum('quantity', filter=Q(location='BOUTIQUE')),
                magasin=Sum('quantity', filter=Q(location='MAGASIN')),
                total=Sum('quantity'),
            )
        )
        return Response(list(rows))


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockMovement.objects.select_related('product', 'shop', 'related_shop', 'created_by').all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, CanCreateStockMovement]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['shop', 'product', 'movement_type', 'location']
    search_fields = ['product__name', 'product__sku', 'reference', 'reason']
    ordering_fields = ['created_at', 'quantity']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()
        user = self.request.user
        if user.is_super_admin:
            return queryset
        if user.shop:
            return queryset.filter(shop=user.shop)
        return queryset.none()

    @action(detail=False, methods=['post'])
    def add_stock(self, request):
        """Enregistrer une entrée de stock (arrivage boutique ou magasin)."""
        data = request.data.copy()
        data['movement_type'] = 'entry'
        if 'quantity' in data:
            data['quantity'] = abs(int(data['quantity']))

        # Par défaut BOUTIQUE sauf si magasinier
        if request.user.is_magasinier and 'location' not in data:
            data['location'] = 'MAGASIN'

        serializer = StockMovementCreateSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        shop_id  = serializer.validated_data['shop'].id
        location = serializer.validated_data.get('location', 'BOUTIQUE')

        if not request.user.is_super_admin:
            if not request.user.shop or request.user.shop.id != shop_id:
                return Response({'error': 'Vous ne pouvez pas ajouter du stock à cette boutique.'}, status=status.HTTP_403_FORBIDDEN)
            if request.user.is_magasinier and location != 'MAGASIN':
                return Response({'error': 'Le magasinier ne peut enregistrer des entrées que dans le magasin.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            movement = serializer.save()
            return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def remove_stock(self, request):
        data = request.data.copy()
        if 'quantity' in data:
            data['quantity'] = -abs(int(data['quantity']))
        if 'movement_type' not in data:
            data['movement_type'] = 'exit'

        serializer = StockMovementCreateSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        shop_id = serializer.validated_data['shop'].id

        if not request.user.is_super_admin:
            if not request.user.shop or request.user.shop.id != shop_id:
                return Response({'error': 'Vous ne pouvez pas retirer du stock de cette boutique.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            movement = serializer.save()
            return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.select_related(
        'from_shop', 'to_shop', 'product', 'created_by', 'received_by'
    ).all()
    permission_classes = [IsAuthenticated, CanManageTransfers]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['from_shop', 'to_shop', 'product', 'status', 'transfer_type']
    search_fields = ['reference', 'product__name', 'product__sku']
    ordering_fields = ['created_at', 'sent_at', 'received_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return StockTransferCreateSerializer
        return StockTransferSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()
        user = self.request.user
        if user.is_super_admin:
            return queryset
        if user.shop:
            return queryset.filter(Q(from_shop=user.shop) | Q(to_shop=user.shop))
        return queryset.none()

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'pending':
            return Response({'error': 'Ce transfert ne peut pas être envoyé.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_super_admin:
            if transfer.from_shop != request.user.shop:
                return Response({'error': 'Vous ne pouvez pas envoyer ce transfert.'}, status=status.HTTP_403_FORBIDDEN)
            # Magasinier ne peut envoyer que les transferts warehouse
            if request.user.is_magasinier and transfer.transfer_type != 'warehouse':
                return Response({'error': 'Le magasinier ne peut envoyer que des transferts magasin→boutique.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            if transfer.transfer_type == 'warehouse':
                # Déduire du stock magasin
                StockMovement.objects.create(
                    product=transfer.product, shop=transfer.from_shop,
                    location='MAGASIN', movement_type='transfer_out',
                    quantity=-transfer.quantity,
                    reference=transfer.reference,
                    reason=f"Sortie magasin → boutique ({transfer.reference})",
                    created_by=request.user,
                )
            else:
                # Inter-boutique: déduire du stock boutique source
                StockMovement.objects.create(
                    product=transfer.product, shop=transfer.from_shop,
                    location='BOUTIQUE', movement_type='transfer_out',
                    quantity=-transfer.quantity,
                    related_shop=transfer.to_shop,
                    reference=transfer.reference,
                    reason=f"Transfert vers {transfer.to_shop.name}",
                    created_by=request.user,
                )
            transfer.status  = 'in_transit'
            transfer.sent_at = timezone.now()
            transfer.save()
            return Response({'message': 'Transfert envoyé avec succès.', 'transfer': StockTransferSerializer(transfer).data})
        except DjangoValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'in_transit':
            return Response({'error': 'Ce transfert ne peut pas être reçu.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_super_admin:
            if transfer.to_shop != request.user.shop:
                return Response({'error': 'Vous ne pouvez pas recevoir ce transfert.'}, status=status.HTTP_403_FORBIDDEN)
            # Magasinier ne peut pas réceptionner (c'est le rôle boutique)
            if request.user.is_magasinier and transfer.transfer_type == 'warehouse':
                return Response({'error': 'Seul le manager ou employé de la boutique peut réceptionner ce transfert.'}, status=status.HTTP_403_FORBIDDEN)

        if transfer.transfer_type == 'warehouse':
            # Ajouter au stock boutique
            StockMovement.objects.create(
                product=transfer.product, shop=transfer.to_shop,
                location='BOUTIQUE', movement_type='transfer_in',
                quantity=transfer.quantity,
                reference=transfer.reference,
                reason=f"Réception depuis magasin ({transfer.reference})",
                created_by=request.user,
            )
        else:
            StockMovement.objects.create(
                product=transfer.product, shop=transfer.to_shop,
                location='BOUTIQUE', movement_type='transfer_in',
                quantity=transfer.quantity,
                related_shop=transfer.from_shop,
                reference=transfer.reference,
                reason=f"Transfert depuis {transfer.from_shop.name}",
                created_by=request.user,
            )

        transfer.status      = 'received'
        transfer.received_at = timezone.now()
        transfer.received_by = request.user
        transfer.save()
        return Response({'message': 'Transfert reçu avec succès.', 'transfer': StockTransferSerializer(transfer).data})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status not in ['pending', 'in_transit']:
            return Response({'error': 'Ce transfert ne peut pas être annulé.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.is_super_admin:
            if transfer.from_shop != request.user.shop:
                return Response({'error': 'Vous ne pouvez pas annuler ce transfert.'}, status=status.HTTP_403_FORBIDDEN)

        if transfer.status == 'in_transit':
            location = 'MAGASIN' if transfer.transfer_type == 'warehouse' else 'BOUTIQUE'
            StockMovement.objects.create(
                product=transfer.product, shop=transfer.from_shop,
                location=location, movement_type='return',
                quantity=transfer.quantity,
                reference=transfer.reference,
                reason=f"Annulation transfert {transfer.reference}",
                created_by=request.user,
            )

        transfer.status = 'cancelled'
        transfer.save()
        return Response({'message': 'Transfert annulé avec succès.', 'transfer': StockTransferSerializer(transfer).data})
