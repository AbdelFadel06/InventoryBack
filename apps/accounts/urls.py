from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.accounts.views import UserViewSet
from apps.accounts.views.auth import PasswordResetRequestView, PasswordResetConfirmView

app_name = 'accounts'

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/password-reset/',         PasswordResetRequestView.as_view(), name='password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]
