from django.contrib import admin
from apps.products.models import Product, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'products_count', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Informations de base', {
            'fields': ('name', 'description', 'parent')
        }),
        ('Statut', {
            'fields': ('is_active',)
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def products_count(self, obj):
        return obj.products.count()
    products_count.short_description = 'Nombre de produits'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'sku', 'name', 'category', 'selling_price', 'unit',
        'shop', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'category', 'shop', 'unit', 'created_at']
    search_fields = ['name', 'sku', 'barcode', 'description']
    readonly_fields = [
        'created_at', 'updated_at', 'profit_margin',
        'profit_amount', 'created_by'
    ]

    fieldsets = (
        ('Informations de base', {
            'fields': ('name', 'description', 'sku', 'barcode', 'category', 'image')
        }),
        ('Prix', {
            'fields': ('cost_price', 'selling_price', 'profit_margin', 'profit_amount', 'unit')
        }),
        ('Gestion du stock', {
            'fields': ('minimum_stock', 'reorder_level')
        }),
        ('Boutique', {
            'fields': ('shop',)
        }),
        ('Statut', {
            'fields': ('is_active',)
        }),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'category', 'shop', 'created_by'
        )
