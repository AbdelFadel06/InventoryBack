# apps/sales/serializers/sale.py
from rest_framework import serializers
from apps.sales.models.sale import CashierSession, Sale, SaleItem, Expense
from decimal import Decimal
from django.db import transaction
from django.utils import timezone


# ── CashierSession ─────────────────────────────────────────────────

class CashierSessionSerializer(serializers.ModelSerializer):
    cashier_name    = serializers.CharField(source='cashier.get_full_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)
    shop_name       = serializers.CharField(source='shop.name', read_only=True)
    is_active       = serializers.BooleanField(read_only=True)
    sales_count     = serializers.SerializerMethodField()
    total_sales     = serializers.SerializerMethodField()

    class Meta:
        model  = CashierSession
        fields = [
            'id', 'shop', 'shop_name', 'cashier', 'cashier_name',
            'created_by', 'created_by_name', 'period_type',
            'start_date', 'end_date', 'status', 'is_active',
            'notes', 'sales_count', 'total_sales',
            'created_at', 'closed_at',
        ]
        read_only_fields = ['id', 'created_at', 'closed_at', 'created_by']

    def get_sales_count(self, obj):
        return obj.sales.filter(status='completed').count()

    def get_total_sales(self, obj):
        from django.db.models import Sum
        return obj.sales.filter(status='completed').aggregate(
            t=Sum('total_amount')
        )['t'] or 0


class CashierSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CashierSession
        fields = ['shop', 'cashier', 'period_type', 'start_date', 'end_date', 'notes']

    def validate(self, attrs):
        # Vérifier que le caissier appartient à la boutique
        cashier = attrs.get('cashier')
        shop    = attrs.get('shop')
        if cashier and shop and cashier.shop != shop:
            raise serializers.ValidationError({
                'cashier': "Ce caissier n'appartient pas à cette boutique."
            })

        # Vérifier qu'il n'y a pas déjà une session active
        from django.db.models import Q
        existing = CashierSession.objects.filter(
            shop=shop, status='active',
            start_date__lte=attrs['end_date'],
            end_date__gte=attrs['start_date'],
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                "Il existe déjà une session active qui chevauche cette période."
            )

        # Vérifier les dates
        if attrs['start_date'] > attrs['end_date']:
            raise serializers.ValidationError(
                {'end_date': "La date de fin doit être après la date de début."}
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return CashierSession.objects.create(**validated_data)


# ── SaleItem ───────────────────────────────────────────────────────

class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_sku  = serializers.CharField(source='product.sku',  read_only=True)
    product_unit = serializers.CharField(source='product.unit', read_only=True)

    class Meta:
        model  = SaleItem
        fields = [
            'id', 'product', 'product_name', 'product_sku', 'product_unit',
            'quantity', 'unit_price',
            'discount_type', 'discount_value', 'discount_amount',
            'subtotal', 'total_price',
        ]
        read_only_fields = ['id', 'discount_amount', 'subtotal', 'total_price']


class SaleItemCreateSerializer(serializers.Serializer):
    product        = serializers.IntegerField()
    quantity       = serializers.IntegerField(min_value=1)
    discount_type  = serializers.ChoiceField(
        choices=['fixed', 'percent'], required=False, allow_null=True
    )
    discount_value = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        required=False, default=Decimal('0.00')
    )


# ── Sale ───────────────────────────────────────────────────────────

class SaleSerializer(serializers.ModelSerializer):
    items          = SaleItemSerializer(many=True, read_only=True)
    cashier_name   = serializers.CharField(source='cashier.get_full_name', read_only=True, allow_null=True)
    livreur_name   = serializers.CharField(source='livreur.get_full_name', read_only=True, allow_null=True)
    shop_name      = serializers.CharField(source='shop.name', read_only=True)
    payment_label  = serializers.CharField(source='get_payment_method_display', read_only=True)
    sale_type_label = serializers.CharField(source='get_sale_type_display', read_only=True)
    items_count    = serializers.SerializerMethodField()

    class Meta:
        model  = Sale
        fields = [
            'id', 'reference', 'shop', 'shop_name', 'session',
            'cashier', 'cashier_name',
            'sale_type', 'sale_type_label',
            'payment_method', 'payment_label', 'payment_status',
            'livreur', 'livreur_name', 'delivery_address', 'delivered_at',
            'subtotal', 'total_discount', 'total_amount',
            'status', 'notes', 'items', 'items_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reference', 'subtotal', 'total_discount',
            'total_amount', 'created_at', 'updated_at'
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class SaleListSerializer(serializers.ModelSerializer):
    cashier_name    = serializers.CharField(source='cashier.get_full_name', read_only=True, allow_null=True)
    livreur_name    = serializers.CharField(source='livreur.get_full_name', read_only=True, allow_null=True)
    payment_label   = serializers.CharField(source='get_payment_method_display', read_only=True)
    sale_type_label = serializers.CharField(source='get_sale_type_display', read_only=True)
    items_count     = serializers.SerializerMethodField()

    class Meta:
        model  = Sale
        fields = [
            'id', 'reference', 'sale_type', 'sale_type_label',
            'cashier', 'cashier_name',
            'payment_method', 'payment_label', 'payment_status',
            'livreur', 'livreur_name',
            'total_discount', 'total_amount',
            'status', 'items_count', 'created_at',
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class SaleCreateSerializer(serializers.Serializer):
    sale_type        = serializers.ChoiceField(choices=['direct', 'delivery'], default='direct')
    payment_method   = serializers.ChoiceField(choices=['cash', 'mobile_money', 'on_delivery'], default='cash')
    livreur          = serializers.IntegerField(required=False, allow_null=True)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    notes            = serializers.CharField(required=False, allow_blank=True)
    items            = SaleItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Au moins un article est requis.")
        return value

    def validate(self, attrs):
        from apps.products.models import Product
        from apps.stocks.models import Stock
        from apps.accounts.models import User

        request = self.context.get('request')
        shop    = request.user.shop

        if not shop:
            raise serializers.ValidationError("Vous n'êtes pas assigné à une boutique.")

        # Vérifier session active
        session = CashierSession.objects.filter(
            shop=shop, status='active',
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date(),
        ).first()

        if not session:
            raise serializers.ValidationError(
                "Aucune session de caisse active. Le manager doit ouvrir une session."
            )

        # Vérifier que l'utilisateur est bien le caissier désigné
        if request.user.role == 'EMPLOYEE' and session.cashier != request.user:
            raise serializers.ValidationError(
                f"Vous n'êtes pas le caissier désigné pour cette session. "
                f"Caissier actuel : {session.cashier.get_full_name()}"
            )

        attrs['_session'] = session

        # Livraison : livreur obligatoire
        if attrs.get('sale_type') == 'delivery':
            if not attrs.get('livreur'):
                raise serializers.ValidationError({'livreur': "Le livreur est obligatoire pour une livraison."})
            try:
                livreur = User.objects.get(id=attrs['livreur'], shop=shop)
                if livreur.role != 'LIVREUR':
                    raise serializers.ValidationError({'livreur': "Cet utilisateur n'est pas un livreur."})
                attrs['_livreur'] = livreur
            except User.DoesNotExist:
                raise serializers.ValidationError({'livreur': "Livreur introuvable."})

            # Paiement livraison
            if attrs.get('payment_method') not in ['cash', 'mobile_money', 'on_delivery']:
                raise serializers.ValidationError({'payment_method': "Moyen de paiement invalide."})

        # Vérifier stock
        for item in attrs['items']:
            try:
                product = Product.objects.get(id=item['product'], is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError(
                    {'items': f"Produit ID {item['product']} introuvable."}
                )
            stock = Stock.objects.filter(product=product, shop=shop).first()
            available = stock.quantity if stock else 0
            if available < item['quantity']:
                raise serializers.ValidationError({
                    'items': f"Stock insuffisant pour {product.name}. "
                             f"Disponible: {available}, demandé: {item['quantity']}"
                })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from apps.products.models import Product
        from apps.stocks.models import StockMovement

        request  = self.context.get('request')
        shop     = request.user.shop
        session  = validated_data.pop('_session')
        livreur  = validated_data.pop('_livreur', None)
        items    = validated_data.pop('items')

        sale_type      = validated_data.get('sale_type', 'direct')
        payment_method = validated_data.get('payment_method', 'cash')
        payment_status = 'pending' if payment_method == 'on_delivery' else 'paid'

        sale = Sale.objects.create(
            session=session,
            shop=shop,
            cashier=request.user,
            sale_type=sale_type,
            payment_method=payment_method,
            payment_status=payment_status,
            livreur=livreur,
            delivery_address=validated_data.get('delivery_address', ''),
            notes=validated_data.get('notes', ''),
        )

        subtotal = Decimal('0.00')
        discount = Decimal('0.00')

        for item_data in items:
            product    = Product.objects.get(id=item_data['product'])
            unit_price = product.selling_price
            quantity   = item_data['quantity']

            sale_item = SaleItem(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                discount_type=item_data.get('discount_type'),
                discount_value=item_data.get('discount_value', Decimal('0.00')),
            )
            sale_item.save()

            subtotal += sale_item.subtotal
            discount += sale_item.discount_amount

            # Décrémenter stock
            StockMovement.objects.create(
                product=product,
                shop=shop,
                movement_type='exit',
                quantity=-quantity,
                reference=sale.reference,
                reason=f"Vente {sale.reference}",
                created_by=request.user,
            )

        sale.subtotal       = subtotal
        sale.total_discount = discount
        sale.total_amount   = subtotal - discount
        sale.save(update_fields=['subtotal', 'total_discount', 'total_amount'])

        return sale


# ── Expense ────────────────────────────────────────────────────────

class ExpenseSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model  = Expense
        fields = ['id', 'session', 'shop', 'label', 'amount', 'sale_date', 'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['id', 'created_at', 'created_by', 'shop']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
            validated_data['shop']       = request.user.shop
        return Expense.objects.create(**validated_data)
