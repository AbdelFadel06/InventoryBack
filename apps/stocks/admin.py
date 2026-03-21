from django.contrib import admin
from apps.stocks.models import Stock, StockMovement, StockTransfer


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'shop', 'quantity', 'stock_status',
        'is_low_stock', 'last_updated'
    ]
    list_filter = ['shop', 'product__category', 'last_updated']
    search_fields = ['product__name', 'product__sku', 'shop__name']
    readonly_fields = [
        'last_updated', 'is_low_stock', 'needs_reorder',
        'stock_status', 'stock_value'
    ]

    fieldsets = (
        ('Informations de base', {
            'fields': ('product', 'shop', 'quantity')
        }),
        ('Statut', {
            'fields': ('is_low_stock', 'needs_reorder', 'stock_status', 'stock_value')
        }),
        ('Métadonnées', {
            'fields': ('last_updated', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'shop', 'updated_by'
        )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'shop', 'movement_type', 'quantity',
        'quantity_before', 'quantity_after', 'created_at', 'created_by'
    ]
    list_filter = ['movement_type', 'shop', 'created_at']
    search_fields = ['product__name', 'product__sku', 'reference', 'reason']
    readonly_fields = [
        'quantity_before', 'quantity_after', 'created_at',
        'total_value', 'created_by'
    ]

    fieldsets = (
        ('Informations de base', {
            'fields': ('product', 'shop', 'movement_type')
        }),
        ('Quantités', {
            'fields': ('quantity', 'quantity_before', 'quantity_after')
        }),
        ('Transfert', {
            'fields': ('related_shop',)
        }),
        ('Détails', {
            'fields': ('reference', 'reason', 'notes', 'unit_price', 'total_value')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'shop', 'related_shop', 'created_by'
        )

    def has_add_permission(self, request):
        # Désactiver l'ajout via l'admin (utiliser l'API)
        return False

    def has_delete_permission(self, request, obj=None):
        # Désactiver la suppression (historique)
        return False


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'product', 'from_shop', 'to_shop',
        'quantity', 'status', 'created_at', 'created_by'
    ]
    list_filter = ['status', 'from_shop', 'to_shop', 'created_at']
    search_fields = ['reference', 'product__name', 'product__sku']
    readonly_fields = [
        'reference', 'created_at', 'sent_at', 'received_at',
        'created_by', 'received_by'
    ]

    fieldsets = (
        ('Informations de base', {
            'fields': ('reference', 'product', 'quantity')
        }),
        ('Boutiques', {
            'fields': ('from_shop', 'to_shop')
        }),
        ('Statut', {
            'fields': ('status', 'notes')
        }),
        ('Dates', {
            'fields': ('created_at', 'sent_at', 'received_at')
        }),
        ('Utilisateurs', {
            'fields': ('created_by', 'received_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'from_shop', 'to_shop', 'created_by', 'received_by'
        )
