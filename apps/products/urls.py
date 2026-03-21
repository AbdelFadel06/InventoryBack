from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.products.views import ProductViewSet, CategoryViewSet

app_name = 'products'

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = [
    path('', include(router.urls)),
]
