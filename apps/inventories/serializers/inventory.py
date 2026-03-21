from rest_framework import serializers
from apps.inventories.models import Inventory, InventoryLine
from django.utils import timezone
import uuid


class InventoryLineSerializer(serializers.ModelSerializer):
    """
    Serializer pour les lignes d'inventaire
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    unit = serializers.CharField(source='product.unit', read_only=True)
    difference = serializers.IntegerField(read_only=True)
    difference_percentage = serializers.FloatField(read_only=True)
    discrepancy_status = serializers.CharField(read_only=True)
    adjustment_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    counted_by_name = serializers.CharField(
        source='counted_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = InventoryLine
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'unit',
            'expected_quantity', 'counted_quantity', 'difference',
            'difference_percentage', 'discrepancy_status',
            'is_counted', 'adjustment_value', 'notes',
            'counted_at', 'counted_by', 'counted_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'expected_quantity', 'is_counted',
            'counted_at', 'counted_by', 'created_at', 'updated_at'
        ]


class InventoryLineCountSerializer(serializers.Serializer):
    """
    Serializer pour enregistrer un comptage
    """
    line_id = serializers.IntegerField(required=True)
    counted_quantity = serializers.IntegerField(min_value=0, required=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class InventorySerializer(serializers.ModelSerializer):
    """
    Serializer complet pour les inventaires
    """
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_products = serializers.IntegerField(read_only=True)
    products_counted = serializers.IntegerField(read_only=True)
    counting_progress = serializers.FloatField(read_only=True)
    total_discrepancies = serializers.IntegerField(read_only=True)
    total_shortage = serializers.IntegerField(read_only=True)
    total_surplus = serializers.IntegerField(read_only=True)
    adjustment_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    validated_by_name = serializers.CharField(
        source='validated_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Inventory
        fields = [
            'id', 'reference', 'shop', 'shop_name', 'inventory_date',
            'status', 'status_display', 'notes',
            'total_products', 'products_counted', 'counting_progress',
            'total_discrepancies', 'total_shortage', 'total_surplus',
            'adjustment_value',
            'created_at', 'updated_at', 'completed_at', 'validated_at',
            'created_by', 'created_by_name', 'validated_by', 'validated_by_name'
        ]
        read_only_fields = [
            'id', 'reference', 'completed_at', 'validated_at',
            'created_at', 'updated_at', 'created_by', 'validated_by'
        ]


class InventoryCreateSerializer(serializers.ModelSerializer):
    """
    Serializer pour créer un inventaire
    """
    class Meta:
        model = Inventory
        fields = ['id', 'reference', 'shop', 'inventory_date', 'notes']
        read_only_fields = ['id', 'reference']

    def validate_inventory_date(self, value):
        """Valider que la date n'est pas dans le futur"""
        if value > timezone.now().date():
            raise serializers.ValidationError(
                "La date d'inventaire ne peut pas être dans le futur."
            )
        return value

    def create(self, validated_data):
        # Générer une référence unique
        date_str = validated_data['inventory_date'].strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:6].upper()
        reference = f"INV-{date_str}-{unique_id}"

        validated_data['reference'] = reference

        # Ajouter l'utilisateur
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        return Inventory.objects.create(**validated_data)


class InventoryDetailSerializer(serializers.ModelSerializer):
    """
    Serializer détaillé avec toutes les lignes
    """
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    lines = InventoryLineSerializer(many=True, read_only=True)
    total_products = serializers.IntegerField(read_only=True)
    products_counted = serializers.IntegerField(read_only=True)
    counting_progress = serializers.FloatField(read_only=True)
    total_discrepancies = serializers.IntegerField(read_only=True)
    total_shortage = serializers.IntegerField(read_only=True)
    total_surplus = serializers.IntegerField(read_only=True)
    adjustment_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    validated_by_name = serializers.CharField(
        source='validated_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Inventory
        fields = [
            'id', 'reference', 'shop', 'shop_name', 'inventory_date',
            'status', 'status_display', 'notes',
            'total_products', 'products_counted', 'counting_progress',
            'total_discrepancies', 'total_shortage', 'total_surplus',
            'adjustment_value', 'lines',
            'created_at', 'updated_at', 'completed_at', 'validated_at',
            'created_by', 'created_by_name', 'validated_by', 'validated_by_name'
        ]


class InventoryListSerializer(serializers.ModelSerializer):
    """
    Serializer minimal pour les listes
    """
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    counting_progress = serializers.FloatField(read_only=True)

    class Meta:
        model = Inventory
        fields = [
            'id', 'reference', 'shop', 'shop_name', 'inventory_date',
            'status', 'status_display', 'counting_progress', 'total_products',
        'products_counted',
            'created_at'
        ]


class InventoryDiscrepancySerializer(serializers.ModelSerializer):
    """
    Serializer pour afficher uniquement les écarts
    """
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    difference = serializers.IntegerField(read_only=True)
    difference_percentage = serializers.FloatField(read_only=True)
    discrepancy_status = serializers.CharField(read_only=True)
    adjustment_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = InventoryLine
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'expected_quantity', 'counted_quantity',
            'difference', 'difference_percentage',
            'discrepancy_status', 'adjustment_value', 'notes'
        ]
