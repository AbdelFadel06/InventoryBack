from django.contrib import admin
from apps.shops.models import Shop


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'city', 'manager', 'phone_number',
        'total_employees', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'city', 'country', 'created_at']
    search_fields = ['name', 'ifu', 'phone_number', 'email', 'city']
    readonly_fields = ['created_at', 'updated_at', 'total_employees', 'active_employees']

    fieldsets = (
        ('Informations de base', {
            'fields': ('name', 'slogan', 'logo', 'ifu')
        }),
        ('Contact', {
            'fields': ('phone_number', 'email')
        }),
        ('Adresse', {
            'fields': ('address', 'city', 'country')
        }),
        ('Management', {
            'fields': ('manager', 'is_active')
        }),
        ('Statistiques', {
            'fields': ('total_employees', 'active_employees'),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('manager', 'created_by')
