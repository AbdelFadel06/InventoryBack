from django.contrib import admin
from apps.inventories.models import Inventory, InventoryLine


class InventoryLineInline(admin.TabularInline):
    model = InventoryLine
    extra = 0
    readonly_fields = ['difference', 'discrepancy_status', 'counted_at', 'counted_by']
    fields = [
        'product', 'expected_quantity', 'counted_quantity',
        'difference', 'is_counted', 'discrepancy_status', 'notes'
    ]


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'shop', 'inventory_date', 'status',
        'counting_progress', 'total_products', 'total_discrepancies',
        'created_at'
    ]
    list_filter = ['status', 'shop', 'inventory_date', 'created_at']
    search_fields = ['reference', 'notes']
    readonly_fields = [
        'reference', 'total_products', 'products_counted', 'counting_progress',
        'total_discrepancies', 'total_shortage', 'total_surplus',
        'adjustment_value', 'created_at', 'updated_at',
        'completed_at', 'validated_at', 'created_by', 'validated_by'
    ]
    inlines = [InventoryLineInline]

    fieldsets = (
        ('Informations de base', {
            'fields': ('reference', 'shop', 'inventory_date', 'status', 'notes')
        }),
        ('Progression', {
            'fields': (
                'total_products', 'products_counted', 'counting_progress'
            )
        }),
        ('Écarts', {
            'fields': (
                'total_discrepancies', 'total_shortage',
                'total_surplus', 'adjustment_value'
            ),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': (
                'created_at', 'updated_at', 'completed_at', 'validated_at'
            ),
            'classes': ('collapse',)
        }),
        ('Utilisateurs', {
            'fields': ('created_by', 'validated_by'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'shop', 'created_by', 'validated_by'
        ).prefetch_related('lines')


@admin.register(InventoryLine)
class InventoryLineAdmin(admin.ModelAdmin):
    list_display = [
        'inventory', 'product', 'expected_quantity',
        'counted_quantity', 'difference', 'discrepancy_status',
        'is_counted'
    ]
    list_filter = ['is_counted', 'inventory__shop', 'inventory__status']
    search_fields = ['product__name', 'product__sku', 'inventory__reference']
    readonly_fields = [
        'difference', 'difference_percentage', 'discrepancy_status',
        'adjustment_value', 'counted_at', 'counted_by',
        'created_at', 'updated_at'
    ]

    fieldsets = (
        ('Informations de base', {
            'fields': ('inventory', 'product')
        }),
        ('Quantités', {
            'fields': (
                'expected_quantity', 'counted_quantity',
                'difference', 'difference_percentage'
            )
        }),
        ('Statut', {
            'fields': ('is_counted', 'discrepancy_status', 'adjustment_value')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Métadonnées', {
            'fields': ('counted_at', 'counted_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'inventory', 'inventory__shop', 'product', 'counted_by'
        )
