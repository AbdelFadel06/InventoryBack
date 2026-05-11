from django.contrib import admin
from apps.shops.models import Shop, ShopAssignment


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'city', 'get_managers', 'phone_number',
        'total_employees', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'city', 'country', 'created_at']
    search_fields = ['name', 'ifu', 'phone_number', 'email', 'city']
    readonly_fields = ['created_at', 'updated_at', 'total_employees', 'active_employees']
    filter_horizontal = ['managers']

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
            'fields': ('managers', 'is_active')
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

    def get_managers(self, obj):
        return ", ".join(m.get_full_name() for m in obj.managers.all())
    get_managers.short_description = "Managers"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('managers').select_related('created_by')


@admin.register(ShopAssignment)
class ShopAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'shop', 'start_date', 'end_date', 'is_active', 'assigned_by']
    list_filter = ['is_active', 'shop', 'start_date']
    search_fields = ['user__first_name', 'user__last_name', 'shop__name']
    readonly_fields = ['created_at']
