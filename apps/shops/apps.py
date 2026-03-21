from django.apps import AppConfig


class ShopsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.shops'
    label = "shops"
    verbose_name = 'Gestion des Boutiques'
