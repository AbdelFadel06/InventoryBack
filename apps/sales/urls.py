from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.sales.views.sale import CashierSessionViewSet, SaleViewSet, ExpenseViewSet

app_name = 'sales'

router = DefaultRouter()
router.register(r'cashier-sessions', CashierSessionViewSet, basename='cashier-session')
router.register(r'sales',            SaleViewSet,           basename='sale')
router.register(r'expenses',         ExpenseViewSet,        basename='expense')

urlpatterns = [
    path('', include(router.urls)),
]
