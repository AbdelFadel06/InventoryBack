from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.shops.views import ShopViewSet

app_name = 'shops'

router = DefaultRouter()
router.register(r'shops', ShopViewSet, basename='shop')

urlpatterns = [
    path('', include(router.urls)),
]
