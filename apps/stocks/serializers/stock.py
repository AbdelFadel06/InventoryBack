from rest_framework import serializers
from apps.stocks.models import Stock, StockMovement, StockTransfer
from apps.products.serializers import ProductListSerializer
from apps.shops.serializers import ShopListSerializer
from django.utils import timezone


class StockSerializer(serializers.ModelSerializer):
    """
    Serializer complet pour les stocks
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_image = serializers.SerializerMethodField()
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    unit = serializers.CharField(source='product.unit', read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    stock_status = serializers.CharField(read_only=True)
    stock_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    minimum_stock = serializers.IntegerField(source='product.minimum_stock', read_only=True)
    reorder_level = serializers.IntegerField(source='product.reorder_level', read_only=True)
    updated_by_name = serializers.CharField(
        source='updated_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    def get_product_image(self, obj):
        img = obj.product.images.filter(is_primary=True).first()
        if img:
            return img.url
        img = obj.product.images.first()
        return img.url if img else None

    class Meta:
        model = Stock
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'product_image',
            'shop', 'shop_name', 'quantity', 'unit',
            'is_low_stock', 'needs_reorder', 'stock_status',
            'minimum_stock', 'reorder_level', 'stock_value',
            'last_updated', 'updated_by', 'updated_by_name'
        ]
        read_only_fields = ['id', 'last_updated']


class StockListSerializer(serializers.ModelSerializer):
    """
    Serializer minimal pour les listes de stocks
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_image = serializers.SerializerMethodField()
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    stock_status = serializers.CharField(read_only=True)
    stock_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    def get_product_image(self, obj):
        img = obj.product.images.filter(is_primary=True).first()
        if img:
            return img.url
        img = obj.product.images.first()
        return img.url if img else None

    class Meta:
        model = Stock
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'product_image',
            'shop', 'shop_name', 'quantity', 'stock_status', 'stock_value'
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    """
    Serializer pour les mouvements de stock
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    related_shop_name = serializers.CharField(
        source='related_shop.name',
        read_only=True,
        allow_null=True
    )
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    movement_type_display = serializers.CharField(
        source='get_movement_type_display',
        read_only=True
    )
    total_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'shop', 'shop_name', 'movement_type', 'movement_type_display',
            'quantity', 'quantity_before', 'quantity_after',
            'related_shop', 'related_shop_name',
            'reference', 'reason', 'notes', 'unit_price', 'total_value',
            'created_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = [
            'id', 'quantity_before', 'quantity_after', 'created_at'
        ]


class StockMovementCreateSerializer(serializers.Serializer):
    """
    Serializer pour créer un mouvement de stock
    """
    product = serializers.IntegerField(required=True)
    shop = serializers.IntegerField(required=True)
    movement_type = serializers.ChoiceField(
        choices=StockMovement.MOVEMENT_TYPES,
        required=True
    )
    quantity = serializers.IntegerField(required=True)
    related_shop = serializers.IntegerField(required=False, allow_null=True)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True
    )

    def validate(self, attrs):
        from apps.products.models import Product
        from apps.shops.models import Shop

        # Valider et récupérer les objets
        product_id = attrs.get('product')
        shop_id = attrs.get('shop')
        related_shop_id = attrs.get('related_shop')

        try:
            product = Product.objects.get(id=product_id, is_active=True)
            attrs['product'] = product
        except Product.DoesNotExist:
            raise serializers.ValidationError({'product': 'Produit introuvable ou inactif.'})

        try:
            shop = Shop.objects.get(id=shop_id, is_active=True)
            attrs['shop'] = shop
        except Shop.DoesNotExist:
            raise serializers.ValidationError({'shop': 'Boutique introuvable ou inactive.'})

        if related_shop_id:
            try:
                related_shop = Shop.objects.get(id=related_shop_id, is_active=True)
                attrs['related_shop'] = related_shop
            except Shop.DoesNotExist:
                raise serializers.ValidationError({'related_shop': 'Boutique liée introuvable ou inactive.'})

        movement_type = attrs.get('movement_type')
        quantity = attrs.get('quantity')
        related_shop = attrs.get('related_shop')

        # Pour les sorties, la quantité doit être négative
        if movement_type in ['exit', 'transfer_out', 'damage']:
            if quantity > 0:
                attrs['quantity'] = -abs(quantity)

        # Pour les entrées, la quantité doit être positive
        elif movement_type in ['entry', 'transfer_in', 'return']:
            if quantity < 0:
                attrs['quantity'] = abs(quantity)

        # Pour les transferts, related_shop est obligatoire
        if movement_type in ['transfer_out', 'transfer_in']:
            if not related_shop:
                raise serializers.ValidationError({
                    'related_shop': 'La boutique liée est requise pour les transferts.'
                })

            # Vérifier que ce n'est pas la même boutique
            if related_shop == shop:
                raise serializers.ValidationError({
                    'related_shop': 'La boutique source et destination doivent être différentes.'
                })

        return attrs

    def create(self, validated_data):
        # Ajouter l'utilisateur
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        # Créer le mouvement (le stock sera mis à jour automatiquement via save())
        movement = StockMovement.objects.create(**validated_data)
        return movement


class StockTransferSerializer(serializers.ModelSerializer):
    """
    Serializer pour les transferts de stock
    """
    from_shop_name = serializers.CharField(source='from_shop.name', read_only=True)
    to_shop_name = serializers.CharField(source='to_shop.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    received_by_name = serializers.CharField(
        source='received_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = StockTransfer
        fields = [
            'id', 'reference', 'from_shop', 'from_shop_name',
            'to_shop', 'to_shop_name', 'product', 'product_name', 'product_sku',
            'quantity', 'status', 'status_display', 'notes',
            'created_at', 'sent_at', 'received_at',
            'created_by', 'created_by_name', 'received_by', 'received_by_name'
        ]
        read_only_fields = [
            'id', 'reference', 'created_at', 'sent_at', 'received_at',
            'created_by', 'received_by'
        ]


class StockTransferCreateSerializer(serializers.ModelSerializer):
    """
    Serializer pour créer un transfert
    """
    class Meta:
        model = StockTransfer
        fields = [
            'from_shop', 'to_shop', 'product', 'quantity', 'notes'
        ]

    def validate(self, attrs):
        # Vérifier que ce n'est pas la même boutique
        if attrs['from_shop'] == attrs['to_shop']:
            raise serializers.ValidationError({
                'to_shop': 'La boutique source et destination doivent être différentes.'
            })

        # Vérifier que le stock est suffisant
        from apps.stocks.models import Stock
        stock = Stock.objects.filter(
            product=attrs['product'],
            shop=attrs['from_shop']
        ).first()

        if not stock or stock.quantity < attrs['quantity']:
            current_stock = stock.quantity if stock else 0
            raise serializers.ValidationError({
                'quantity': f'Stock insuffisant. Stock actuel: {current_stock}'
            })

        return attrs

    def create(self, validated_data):
        # Générer une référence unique
        import uuid
        reference = f"TRF-{uuid.uuid4().hex[:8].upper()}"
        validated_data['reference'] = reference

        # Ajouter l'utilisateur
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        return StockTransfer.objects.create(**validated_data)


class StockAdjustmentSerializer(serializers.Serializer):
    """
    Serializer pour les ajustements de stock
    """
    product = serializers.IntegerField(required=True)
    shop = serializers.IntegerField(required=True)
    new_quantity = serializers.IntegerField(
        min_value=0,
        required=True
    )
    reason = serializers.CharField(required=True)

    def validate(self, attrs):
        from apps.products.models import Product
        from apps.shops.models import Shop

        # Valider et récupérer les objets
        product_id = attrs.get('product')
        shop_id = attrs.get('shop')

        try:
            product = Product.objects.get(id=product_id, is_active=True)
            attrs['product'] = product
        except Product.DoesNotExist:
            raise serializers.ValidationError({'product': 'Produit introuvable ou inactif.'})

        try:
            shop = Shop.objects.get(id=shop_id, is_active=True)
            attrs['shop'] = shop
        except Shop.DoesNotExist:
            raise serializers.ValidationError({'shop': 'Boutique introuvable ou inactive.'})

        return attrs


class StockAlertSerializer(serializers.ModelSerializer):
    """
    Serializer pour les alertes de stock
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    category_name = serializers.CharField(source='product.category.name', read_only=True, allow_null=True)
    stock_status = serializers.CharField(read_only=True)

    class Meta:
        model = Stock
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'category_name', 'shop', 'shop_name',
            'quantity', 'stock_status',
            'minimum_stock', 'reorder_level'
        ]

    minimum_stock = serializers.IntegerField(source='product.minimum_stock', read_only=True)
    reorder_level = serializers.IntegerField(source='product.reorder_level', read_only=True)
