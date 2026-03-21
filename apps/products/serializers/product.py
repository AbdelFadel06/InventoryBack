from rest_framework import serializers
from apps.products.models import Product, Category
from decimal import Decimal


class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer pour les catégories
    """
    full_path = serializers.CharField(read_only=True)
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'description', 'parent', 'full_path',
            'is_active', 'products_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_products_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductSerializer(serializers.ModelSerializer):
    """
    Serializer complet pour les produits
    """
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True, allow_null=True)
    profit_margin = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    profit_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    current_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'sku', 'barcode',
            'category', 'category_name', 'image',
            'cost_price', 'selling_price', 'profit_margin', 'profit_amount',
            'unit', 'minimum_stock', 'reorder_level',
            'shop', 'shop_name', 'is_active',
            'current_stock', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def get_current_stock(self, obj):
        """Retourne le stock actuel du produit"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            user = request.user
            # Si l'utilisateur a une boutique, retourner le stock de sa boutique
            if user.shop:
                return obj.get_current_stock(shop=user.shop)
        # Sinon retourner le stock total
        return obj.get_current_stock()

    def validate_sku(self, value):
        """Valider que le SKU est unique"""
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Le code SKU est obligatoire.")
        return value

    def validate_barcode(self, value):
        """Valider le code-barres"""
        if value:
            value = value.strip()
            if not value:
                return None
        return value

    def validate(self, attrs):
        """Validation globale"""
        # Vérifier que le prix de vente >= prix d'achat
        cost_price = attrs.get('cost_price', getattr(self.instance, 'cost_price', None))
        selling_price = attrs.get('selling_price', getattr(self.instance, 'selling_price', None))

        if cost_price and selling_price:
            if selling_price < cost_price:
                raise serializers.ValidationError({
                    'selling_price': 'Le prix de vente ne peut pas être inférieur au prix d\'achat.'
                })

        # Vérifier que minimum_stock <= reorder_level
        minimum_stock = attrs.get('minimum_stock', getattr(self.instance, 'minimum_stock', None))
        reorder_level = attrs.get('reorder_level', getattr(self.instance, 'reorder_level', None))

        if minimum_stock and reorder_level:
            if minimum_stock > reorder_level:
                raise serializers.ValidationError({
                    'minimum_stock': 'Le stock minimum doit être inférieur ou égal au niveau de réapprovisionnement.'
                })

        return attrs

    def validate_image(self, value):
        """Valider la taille de l'image"""
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "La taille de l'image ne doit pas dépasser 5MB."
            )
        return value


class ProductCreateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la création de produits
    """
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'sku', 'barcode',
            'category', 'image', 'cost_price', 'selling_price',
            'unit', 'minimum_stock', 'reorder_level', 'shop'
        ]

    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Le code SKU est obligatoire.")
        return value

    def validate(self, attrs):
        # Validation du prix
        if attrs['selling_price'] < attrs['cost_price']:
            raise serializers.ValidationError({
                'selling_price': 'Le prix de vente ne peut pas être inférieur au prix d\'achat.'
            })

        # Validation des seuils
        if attrs['minimum_stock'] > attrs['reorder_level']:
            raise serializers.ValidationError({
                'minimum_stock': 'Le stock minimum doit être inférieur ou égal au niveau de réapprovisionnement.'
            })

        return attrs

    def create(self, validated_data):
        # Ajouter l'utilisateur qui crée le produit
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

            # Si l'utilisateur a une boutique et shop n'est pas fourni
            if not validated_data.get('shop') and request.user.shop:
                validated_data['shop'] = request.user.shop

        return Product.objects.create(**validated_data)


class ProductUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la mise à jour de produits
    """
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'barcode', 'category', 'image',
            'cost_price', 'selling_price', 'unit',
            'minimum_stock', 'reorder_level', 'is_active'
        ]

    def validate(self, attrs):
        # Validation du prix
        cost_price = attrs.get('cost_price', self.instance.cost_price)
        selling_price = attrs.get('selling_price', self.instance.selling_price)

        if selling_price < cost_price:
            raise serializers.ValidationError({
                'selling_price': 'Le prix de vente ne peut pas être inférieur au prix d\'achat.'
            })

        # Validation des seuils
        minimum_stock = attrs.get('minimum_stock', self.instance.minimum_stock)
        reorder_level = attrs.get('reorder_level', self.instance.reorder_level)

        if minimum_stock > reorder_level:
            raise serializers.ValidationError({
                'minimum_stock': 'Le stock minimum doit être inférieur ou égal au niveau de réapprovisionnement.'
            })

        return attrs


class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializer minimal pour les listes de produits
    """
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True, allow_null=True)
    current_stock = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode', 'image',
            'category', 'category_name','cost_price', 'selling_price',
            'unit', 'shop', 'shop_name', 'is_active',
            'current_stock', 'is_low_stock'
        ]

    def get_current_stock(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            return obj.get_current_stock(shop=request.user.shop)
        return obj.get_current_stock()

    def get_is_low_stock(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            return obj.is_low_stock(shop=request.user.shop)
        return obj.is_low_stock()


class ProductStockAlertSerializer(serializers.ModelSerializer):
    """
    Serializer pour les alertes de stock
    """
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True, allow_null=True)
    current_stock = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'category_name', 'shop_name',
            'minimum_stock', 'reorder_level', 'current_stock', 'stock_status'
        ]

    def get_current_stock(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            return obj.get_current_stock(shop=request.user.shop)
        return obj.get_current_stock()

    def get_stock_status(self, obj):
        current_stock = self.get_current_stock(obj)
        if current_stock == 0:
            return 'out_of_stock'
        elif current_stock < obj.minimum_stock:
            return 'critical'
        elif current_stock <= obj.reorder_level:
            return 'low'
        return 'ok'
