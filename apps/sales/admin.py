from django.contrib import admin
from apps.sales.models.sale import CashierSession, Sale, SaleItem, Expense


@admin.register(CashierSession)
class CashierSessionAdmin(admin.ModelAdmin):
    list_display  = ['shop', 'cashier', 'period_type', 'start_date', 'end_date', 'status', 'created_at']
    list_filter   = ['shop', 'status', 'period_type']
    search_fields = ['cashier__email', 'cashier__first_name', 'cashier__last_name']
    readonly_fields = ['created_at', 'closed_at', 'created_by']

    fieldsets = (
        ('Configuration', {
            'fields': ('shop', 'cashier', 'period_type', 'start_date', 'end_date')
        }),
        ('Statut', {'fields': ('status', 'notes')}),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at', 'closed_at'),
            'classes': ('collapse',)
        }),
    )


class SaleItemInline(admin.TabularInline):
    model           = SaleItem
    extra           = 0
    readonly_fields = ['unit_price', 'subtotal', 'discount_amount', 'total_price']
    fields          = ['product', 'quantity', 'unit_price', 'discount_type', 'discount_value', 'discount_amount', 'subtotal', 'total_price']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display  = [
        'reference', 'shop', 'cashier_name', 'sale_type',
        'payment_method', 'payment_status', 'total_amount', 'status', 'created_at'
    ]
    list_filter   = ['shop', 'status', 'sale_type', 'payment_method', 'payment_status', 'created_at']
    search_fields = ['reference', 'cashier__email', 'cashier__first_name']
    readonly_fields = ['reference', 'subtotal', 'total_discount', 'total_amount', 'created_at', 'updated_at']
    inlines = [SaleItemInline]

    fieldsets = (
        ('Vente', {'fields': ('reference', 'session', 'shop', 'cashier')}),
        ('Type & Paiement', {'fields': ('sale_type', 'payment_method', 'payment_status')}),
        ('Livraison', {'fields': ('livreur', 'delivery_address', 'delivered_at')}),
        ('Montants', {'fields': ('subtotal', 'total_discount', 'total_amount')}),
        ('Statut', {'fields': ('status', 'notes')}),
        ('Métadonnées', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def cashier_name(self, obj):
        return obj.cashier.get_full_name() if obj.cashier else "—"
    cashier_name.short_description = "Caissier"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('shop', 'cashier', 'livreur', 'session')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display  = ['label', 'shop', 'amount', 'sale_date', 'created_by', 'created_at']
    list_filter   = ['shop', 'sale_date']
    search_fields = ['label']
    readonly_fields = ['created_at', 'created_by', 'shop']
