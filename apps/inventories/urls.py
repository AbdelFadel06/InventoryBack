from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.inventories.views import InventoryViewSet

app_name = 'inventories'

router = DefaultRouter()
router.register(r'inventories', InventoryViewSet, basename='inventory')

urlpatterns = [
    path('', include(router.urls)),
]
