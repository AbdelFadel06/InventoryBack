from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum, Count, F, DecimalField
from django_filters.rest_framework import DjangoFilterBackend

from apps.products.models import Product, Category
from apps.products.serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductCreateSerializer,
    ProductUpdateSerializer,
    ProductListSerializer,
    ProductStockAlertSerializer
)
from apps.products.permissions import CanManageProducts, CanManageCategories
from apps.accounts.permissions import IsSuperAdmin


class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les catégories de produits
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, CanManageCategories]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Pour Swagger
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        # Filtrer par statut actif
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Filtrer par catégorie parente
        parent_id = self.request.query_params.get('parent')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)

        return queryset

    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """
        Liste des produits d'une catégorie
        GET /api/categories/{id}/products/
        """
        category = self.get_object()
        products = category.products.filter(is_active=True)

        # Filtrer selon l'utilisateur
        user = request.user
        if not user.is_super_admin:
            if user.shop:
                products = products.filter(Q(shop=user.shop) | Q(shop__isnull=True))
            else:
                products = products.filter(shop__isnull=True)

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({
            'category': category.name,
            'products_count': products.count(),
            'products': serializer.data
        })


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les produits

    Permissions:
    - list/retrieve: Tous les utilisateurs authentifiés
    - create/update/delete: Super Admin ou Shop Manager
    """
    queryset = Product.objects.select_related('category', 'shop', 'created_by').all()
    permission_classes = [IsAuthenticated, CanManageProducts]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'shop', 'is_active', 'unit']
    search_fields = ['name', 'sku', 'barcode', 'description']
    ordering_fields = ['name', 'sku', 'selling_price', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'create':
            return ProductCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ProductUpdateSerializer
        elif self.action == 'list':
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Pour Swagger
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        user = self.request.user

        # Super Admin voit tous les produits
        if user.is_super_admin:
            return queryset

        # Shop Manager et Employee voient les produits de leur boutique
        # + les produits communs (sans boutique assignée)
        if user.shop:
            return queryset.filter(Q(shop=user.shop) | Q(shop__isnull=True))

        # Utilisateurs sans boutique voient que les produits communs
        return queryset.filter(shop__isnull=True)

    def perform_create(self, serializer):
        """Créer un produit"""
        serializer.save()

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """
        Liste des produits avec stock bas
        GET /api/products/low_stock/
        """
        user = request.user
        products = self.get_queryset().filter(is_active=True)

        # Filtrer les produits avec stock bas
        low_stock_products = []
        for product in products:
            shop = user.shop if user.shop else None
            if product.is_low_stock(shop):
                low_stock_products.append(product)

        serializer = ProductStockAlertSerializer(
            low_stock_products,
            many=True,
            context={'request': request}
        )

        return Response({
            'total': len(low_stock_products),
            'products': serializer.data
        })

    @action(detail=False, methods=['get'])
    def out_of_stock(self, request):
        """
        Liste des produits en rupture de stock
        GET /api/products/out_of_stock/
        """
        user = request.user
        products = self.get_queryset().filter(is_active=True)

        # Filtrer les produits en rupture
        out_of_stock_products = []
        for product in products:
            shop = user.shop if user.shop else None
            if product.get_current_stock(shop) == 0:
                out_of_stock_products.append(product)

        serializer = ProductStockAlertSerializer(
            out_of_stock_products,
            many=True,
            context={'request': request}
        )

        return Response({
            'total': len(out_of_stock_products),
            'products': serializer.data
        })

    @action(detail=False, methods=['get'])
    def needs_reorder(self, request):
        """
        Liste des produits qui doivent être réapprovisionnés
        GET /api/products/needs_reorder/
        """
        user = request.user
        products = self.get_queryset().filter(is_active=True)

        # Filtrer les produits à réapprovisionner
        reorder_products = []
        for product in products:
            shop = user.shop if user.shop else None
            if product.needs_reorder(shop):
                reorder_products.append(product)

        serializer = ProductStockAlertSerializer(
            reorder_products,
            many=True,
            context={'request': request}
        )

        return Response({
            'total': len(reorder_products),
            'products': serializer.data
        })

    @action(detail=True, methods=['get'])
    def stock_by_shop(self, request, pk=None):
        """
        Voir le stock d'un produit par boutique
        GET /api/products/{id}/stock_by_shop/
        """
        product = self.get_object()

        # Importer Stock model
        from apps.stocks.models import Stock

        stocks = Stock.objects.filter(product=product).select_related('shop')

        stock_data = []
        for stock in stocks:
            stock_data.append({
                'shop_id': stock.shop.id if stock.shop else None,
                'shop_name': stock.shop.name if stock.shop else 'Stock global',
                'quantity': stock.quantity,
                'is_low_stock': stock.quantity < product.minimum_stock,
                'needs_reorder': stock.quantity <= product.reorder_level
            })

        return Response({
            'product': product.name,
            'sku': product.sku,
            'minimum_stock': product.minimum_stock,
            'reorder_level': product.reorder_level,
            'stocks': stock_data,
            'total_stock': sum(s['quantity'] for s in stock_data)
        })

    @action(detail=False, methods=['post'], permission_classes=[IsSuperAdmin])
    def bulk_update_prices(self, request):
        """
        Mise à jour en masse des prix
        POST /api/products/bulk_update_prices/

        Body:
        {
            "product_ids": [1, 2, 3],
            "percentage_increase": 10.5  // Augmentation en %
        }
        """
        product_ids = request.data.get('product_ids', [])
        percentage = request.data.get('percentage_increase')

        if not product_ids or percentage is None:
            return Response(
                {'error': 'product_ids et percentage_increase sont requis.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            percentage = float(percentage)
        except ValueError:
            return Response(
                {'error': 'percentage_increase doit être un nombre.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        products = Product.objects.filter(id__in=product_ids)
        updated_count = 0

        for product in products:
            # Augmenter les prix
            product.cost_price = product.cost_price * (1 + percentage / 100)
            product.selling_price = product.selling_price * (1 + percentage / 100)
            product.save()
            updated_count += 1

        return Response({
            'message': f'{updated_count} produits mis à jour avec succès.',
            'percentage_increase': percentage
        })

    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """
        Activer/Désactiver un produit
        POST /api/products/{id}/toggle_active/
        """
        product = self.get_object()

        # Vérifier les permissions
        if not request.user.is_super_admin:
            if product.shop and product.shop != request.user.shop:
                return Response(
                    {'error': 'Vous ne pouvez pas modifier ce produit.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        product.is_active = not product.is_active
        product.save()

        return Response({
            'message': f'Produit "{product.name}" {"activé" if product.is_active else "désactivé"} avec succès.',
            'is_active': product.is_active
        })

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Statistiques sur les produits
        GET /api/products/statistics/
        """
        queryset = self.get_queryset()

        total_products = queryset.count()
        active_products = queryset.filter(is_active=True).count()
        inactive_products = total_products - active_products

        # Par catégorie
        products_by_category = queryset.values('category__name').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        # Produits les plus chers
        expensive_products = queryset.order_by('-selling_price')[:5]

        return Response({
            'total_products': total_products,
            'active_products': active_products,
            'inactive_products': inactive_products,
            'products_by_category': list(products_by_category),
            'top_expensive_products': ProductListSerializer(
                expensive_products,
                many=True,
                context={'request': request}
            ).data
        })
