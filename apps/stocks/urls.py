from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.stocks.views import StockViewSet, StockMovementViewSet, StockTransferViewSet

app_name = 'stocks'

router = DefaultRouter()
router.register(r'stocks', StockViewSet, basename='stock')
router.register(r'stock-movements', StockMovementViewSet, basename='stock-movement')
router.register(r'stock-transfers', StockTransferViewSet, basename='stock-transfer')

urlpatterns = [
    path('', include(router.urls)),
]
