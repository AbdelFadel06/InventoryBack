from rest_framework import serializers
from apps.products.models import Product, Category, ProductImage
from decimal import Decimal
import uuid


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'url', 'is_primary', 'order']

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
    images = ProductImageSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'sku', 'barcode',
            'category', 'category_name',
            'images', 'primary_image',
            'cost_price', 'selling_price', 'profit_margin', 'profit_amount',
            'unit', 'minimum_stock', 'reorder_level',
            'shop', 'shop_name', 'is_active',
            'current_stock', 'created_at', 'updated_at',
            'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def get_current_stock(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.shop:
            return obj.get_current_stock(shop=request.user.shop)
        return obj.get_current_stock()

    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        return img.url if img else None

    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Le code SKU est obligatoire.")
        return value

    def validate_barcode(self, value):
        if value:
            value = value.strip()
            if not value:
                return None
        return value

    def validate(self, attrs):
        cost_price = attrs.get('cost_price', getattr(self.instance, 'cost_price', None))
        selling_price = attrs.get('selling_price', getattr(self.instance, 'selling_price', None))
        if cost_price and selling_price and selling_price < cost_price:
            raise serializers.ValidationError({
                'selling_price': "Le prix de vente ne peut pas être inférieur au prix d'achat."
            })
        minimum_stock = attrs.get('minimum_stock', getattr(self.instance, 'minimum_stock', None))
        reorder_level = attrs.get('reorder_level', getattr(self.instance, 'reorder_level', None))
        if minimum_stock and reorder_level and minimum_stock > reorder_level:
            raise serializers.ValidationError({
                'minimum_stock': "Le stock minimum doit être inférieur ou égal au niveau de réapprovisionnement."
            })
        return attrs

class ProductCreateSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    # URLs Cloudinary pour les images (envoyées depuis le frontend)
    image_urls = serializers.ListField(
        child=serializers.URLField(), required=False, write_only=True, default=list
    )

    class Meta:
        model = Product
        fields = [
            'name', 'description', 'sku', 'barcode',
            'category', 'cost_price', 'selling_price',
            'unit', 'minimum_stock', 'reorder_level', 'shop',
            'image_urls',
        ]

    def validate_sku(self, value):
        if value:
            return value.strip().upper()
        return ""

    def create(self, validated_data):
        request = self.context.get('request')
        image_urls = validated_data.pop('image_urls', [])

        sku = (validated_data.get('sku') or '').strip()
        if not sku:
            name = validated_data.get('name', '')
            prefix = ''.join(word[0].upper() for word in name.split()[:3] if word) or 'PRD'
            unique_id = uuid.uuid4().hex[:6].upper()
            sku = f"{prefix}-{unique_id}"
            while Product.objects.filter(sku=sku).exists():
                sku = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

        validated_data['sku'] = sku

        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
            if not validated_data.get('shop') and request.user.shop:
                validated_data['shop'] = request.user.shop

        product = Product.objects.create(**validated_data)

        for i, url in enumerate(image_urls):
            ProductImage.objects.create(product=product, url=url, order=i, is_primary=(i == 0))

        return product

class ProductUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'barcode', 'category',
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
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'sku', 'barcode',
            'primary_image',
            'category', 'category_name', 'cost_price', 'selling_price',
            'unit', 'shop', 'shop_name', 'is_active',
            'current_stock', 'is_low_stock'
        ]

    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        return img.url if img else None

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
