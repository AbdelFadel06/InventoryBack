from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'email', 'first_name', 'last_name', 'role',
        'shop', 'is_active', 'created_at'
    ]
    list_filter = ['role', 'is_active', 'gender', 'shop']
    search_fields = ['email', 'first_name', 'last_name', 'phone_number']
    ordering = ['-created_at']

    fieldsets = (
        ('Informations de connexion', {
            'fields': ('email', 'username', 'password')
        }),
        ('Informations personnelles', {
            'fields': (
                'first_name', 'last_name', 'phone_number',
                'gender', 'date_of_birth', 'profile_picture'
            )
        }),
        ('Rôle et Boutique', {
            'fields': ('role', 'shop')
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Dates importantes', {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')
        }),
    )

    add_fieldsets = (
        ('Informations de connexion', {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
        ('Informations personnelles', {
            'fields': ('first_name', 'last_name', 'phone_number', 'gender', 'date_of_birth')
        }),
        ('Rôle et Boutique', {
            'fields': ('role', 'shop')
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'last_login', 'date_joined']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('shop')
