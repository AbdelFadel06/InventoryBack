from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum, Count, F, DecimalField
from django_filters.rest_framework import DjangoFilterBackend

from apps.products.models import Product, Category, ProductImage
from apps.products.serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductImageSerializer,
    ProductCreateSerializer,
    ProductUpdateSerializer,
    ProductListSerializer,
    ProductStockAlertSerializer
)
from apps.products.permissions import CanManageProducts, CanManageCategories
from apps.accounts.permissions import IsSuperAdmin
from apps.shops.mixins import ActiveShopMixin
from apps.stocks.models import Stock


class CategoryViewSet(ActiveShopMixin, viewsets.ModelViewSet):
    """
    ViewSet pour gérer les catégories de produits — filtrées par boutique active
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

        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        # Filtrer par boutique active
        if not self.request.user.is_super_admin:
            active_shop = self.get_active_shop(self.request)
            if active_shop:
                queryset = queryset.filter(shop=active_shop)
            else:
                queryset = queryset.filter(shop__isnull=True)

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        parent_id = self.request.query_params.get('parent')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)

        return queryset

    def perform_create(self, serializer):
        active_shop = self.get_active_shop(self.request)
        serializer.save(shop=active_shop)

    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """
        Liste des produits d'une catégorie
        GET /api/categories/{id}/products/
        """
        category = self.get_object()
        products = category.products.filter(is_active=True)

        if not request.user.is_super_admin:
            active_shop = self.get_active_shop(request)
            if active_shop:
                products = products.filter(Q(shop=active_shop) | Q(shop__isnull=True))
            else:
                products = products.filter(shop__isnull=True)

        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({
            'category': category.name,
            'products_count': products.count(),
            'products': serializer.data
        })


class ProductViewSet(ActiveShopMixin, viewsets.ModelViewSet):
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
            pass
        else:
            # Shop Manager et Employee voient les produits de la boutique active
            # + les produits communs (sans boutique assignée)
            active_shop = self.get_active_shop(self.request)
            if active_shop:
                queryset = queryset.filter(Q(shop=active_shop) | Q(shop__isnull=True))
            else:
                queryset = queryset.filter(shop__isnull=True)

        has_barcode = self.request.query_params.get('has_barcode')
        if has_barcode is not None:
            if has_barcode.lower() == 'false':
                queryset = queryset.filter(barcode__isnull=True)
            elif has_barcode.lower() == 'true':
                queryset = queryset.exclude(barcode__isnull=True)

        # Filtre pour les codes-barres anciens (format SHM généré par le système)
        has_legacy = self.request.query_params.get('has_legacy_barcode')
        if has_legacy is not None:
            if has_legacy.lower() == 'true':
                queryset = queryset.filter(barcode__startswith='SHM')
            elif has_legacy.lower() == 'false':
                queryset = queryset.exclude(barcode__startswith='SHM')

        return queryset

    @action(detail=False, methods=['get'], url_path='find_duplicates')
    def find_duplicates(self, request):
        """
        Retourne les produits en doublon (même nom + même boutique).
        GET /api/products/find_duplicates/
        """
        from django.db.models import Count as DjCount

        qs = self.get_queryset()

        # Groupes (name, shop) qui apparaissent plus d'une fois
        dup_groups = (
            qs.values('name', 'shop')
              .annotate(cnt=DjCount('id'))
              .filter(cnt__gt=1)
        )

        # Récupérer tous les produits appartenant à ces groupes
        from django.db.models import Q
        filter_q = Q()
        for g in dup_groups:
            filter_q |= Q(name=g['name'], shop=g['shop'])

        if not filter_q:
            return Response({'count': 0, 'results': []})

        duplicates = (
            qs.filter(filter_q)
              .order_by('name', 'shop', 'created_at')
        )

        serializer = ProductListSerializer(duplicates, many=True, context={'request': request})
        return Response({'count': duplicates.count(), 'results': serializer.data})

    def perform_create(self, serializer):
        active_shop = self.get_active_shop(self.request)
        product = serializer.save(shop=active_shop)
        if active_shop:
            Stock.objects.get_or_create(
                product=product, shop=active_shop, location='BOUTIQUE',
                defaults={'quantity': 0},
            )

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
            shop = self.get_active_shop(self.request)
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
            shop = self.get_active_shop(self.request)
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
            shop = self.get_active_shop(self.request)
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
            if product.shop and product.shop != self.get_active_shop(request):
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

    @action(detail=True, methods=['post'], url_path='add_image')
    def add_image(self, request, pk=None):
        """
        Ajouter une image Cloudinary à un produit
        POST /api/products/{id}/add_image/
        Body: { "url": "https://res.cloudinary.com/...", "is_primary": false }
        """
        product = self.get_object()
        url = request.data.get('url')
        if not url:
            return Response({'error': 'URL requise.'}, status=status.HTTP_400_BAD_REQUEST)
        is_primary = request.data.get('is_primary', not product.images.exists())
        order = product.images.count()
        image = ProductImage.objects.create(
            product=product, url=url, is_primary=is_primary, order=order
        )
        return Response(ProductImageSerializer(image).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _make_ean13(product_id: int) -> str:
        """Génère un EAN-13 valide avec préfixe interne 200 (réservé GS1)."""
        base = f"200{product_id:09d}"  # 12 chiffres
        total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(base))
        check = (10 - (total % 10)) % 10
        return base + str(check)

    @staticmethod
    def _is_ean13(value: str) -> bool:
        return bool(value and value.isdigit() and len(value) == 13)

    @staticmethod
    def _is_system_barcode(value: str) -> bool:
        """Retourne True si le code a été généré par le système (ancien SHM... ou EAN-13 interne 200...)."""
        if not value:
            return False
        # Ancien format système
        if value.startswith('SHM'):
            return True
        # EAN-13 généré par notre système (préfixe interne 200)
        if value.isdigit() and len(value) == 13 and value.startswith('200'):
            return True
        return False

    @action(detail=False, methods=['post'], url_path='generate_all_barcodes')
    def generate_all_barcodes(self, request):
        """
        Génère des EAN-13 pour les produits sans code-barres.
        POST /api/products/generate_all_barcodes/
        Param optionnel: ?force=true → remplace aussi les anciens codes SHM...
        Les codes saisis manuellement (fournisseur, etc.) ne sont jamais touchés.
        """
        force = request.query_params.get('force', '').lower() == 'true'
        qs = self.get_queryset().filter(is_active=True)
        updated = []
        for p in qs:
            if p.barcode is None:
                # Pas de code → toujours générer
                p.barcode = self._make_ean13(p.id)
                updated.append(p)
            elif force and self._is_system_barcode(p.barcode):
                # Ancien code système → remplacer seulement si force=true
                p.barcode = self._make_ean13(p.id)
                updated.append(p)
            # Sinon : code saisi manuellement → ne pas toucher
        if updated:
            Product.objects.bulk_update(updated, ['barcode'])
        return Response({
            'generated': len(updated),
            'barcodes': [{'id': p.id, 'name': p.name, 'barcode': p.barcode} for p in updated],
        })

    @action(detail=True, methods=['post'], url_path='generate_barcode')
    def generate_barcode(self, request, pk=None):
        """
        Génère un EAN-13 pour un produit.
        POST /api/products/{id}/generate_barcode/
        - Sans ?force : génère seulement si pas de code, ou si c'est un ancien SHM...
        - Avec ?force=true : génère même si le produit a un code manuel
        Les codes manuels (fournisseur) ne sont jamais écrasés sans ?force=true explicite.
        """
        product = self.get_object()
        force = request.query_params.get('force', '').lower() == 'true'
        if product.barcode:
            if force or self._is_system_barcode(product.barcode):
                # Remplacer : soit force explicite, soit c'est un code système
                pass
            else:
                # Code manuel existant → ne pas toucher
                return Response({'barcode': product.barcode}, status=status.HTTP_200_OK)
        product.barcode = self._make_ean13(product.id)
        product.save(update_fields=['barcode'])
        return Response({'barcode': product.barcode}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='by_barcode')
    def by_barcode(self, request):
        """
        Recherche un produit par code-barres (pour la caisse).
        GET /api/products/by_barcode/?code=SHM00000001
        """
        code = request.query_params.get('code', '').strip()
        if not code:
            return Response({'error': 'Paramètre code requis.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = self.get_queryset().get(barcode=code, is_active=True)
        except Product.DoesNotExist:
            return Response({'error': 'Produit introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProductListSerializer(product, context={'request': request}).data)

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        total_stock = Stock.objects.filter(product=product).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        if total_stock > 0:
            return Response(
                {
                    'error': (
                        f'Impossible de supprimer "{product.name}" : '
                        f'ce produit a encore {total_stock} unité(s) en stock. '
                        f'Retirez le stock avant de supprimer l\'article.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['delete'], url_path=r'remove_image/(?P<image_id>[^/.]+)')
    def remove_image(self, request, pk=None, image_id=None):
        """
        Supprimer une image d'un produit
        DELETE /api/products/{id}/remove_image/{image_id}/
        """
        product = self.get_object()
        try:
            image = product.images.get(pk=image_id)
        except ProductImage.DoesNotExist:
            return Response({'error': 'Image introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        was_primary = image.is_primary
        image.delete()
        # Si c'était l'image principale, promouvoir la suivante
        if was_primary:
            next_img = product.images.first()
            if next_img:
                next_img.is_primary = True
                next_img.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
