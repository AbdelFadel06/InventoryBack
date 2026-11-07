from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PushSubscription
from .push import is_configured, notify_user

MANAGERS_ONLY = "Les notifications sur téléphone sont réservées aux managers."


class SubscriptionSerializer(serializers.Serializer):
    """Format envoyé par le navigateur : {endpoint, keys: {p256dh, auth}}."""
    endpoint = serializers.URLField(max_length=1000)
    keys = serializers.DictField(child=serializers.CharField(max_length=200))

    def validate_keys(self, value):
        if not value.get('p256dh') or not value.get('auth'):
            raise serializers.ValidationError("Clés d'abonnement manquantes.")
        return value

    def validate_endpoint(self, value):
        if not value.startswith('https://'):
            raise serializers.ValidationError("Adresse d'abonnement invalide.")
        return value


class PushKeyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'public_key': settings.VAPID_PUBLIC_KEY if is_configured() else '',
            'allowed': request.user.role == 'SHOP_MANAGER',
        })


class PushSubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'SHOP_MANAGER':
            return Response({'error': MANAGERS_ONLY}, status=status.HTTP_403_FORBIDDEN)
        serializer = SubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        PushSubscription.objects.update_or_create(
            endpoint=data['endpoint'],
            defaults={
                'user': request.user,
                'p256dh': data['keys']['p256dh'],
                'auth': data['keys']['auth'],
                'user_agent': request.headers.get('User-Agent', '')[:255],
            },
        )
        return Response({'subscribed': True}, status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        PushSubscription.objects.filter(user=request.user, endpoint=request.data.get('endpoint', '')).delete()
        return Response({'subscribed': False})


class PushTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'SHOP_MANAGER':
            return Response({'error': MANAGERS_ONLY}, status=status.HTTP_403_FORBIDDEN)
        sent = notify_user(
            request.user, "ShopM", "Les notifications fonctionnent sur cet appareil.", '/manager/dashboard',
        )
        return Response({'devices': sent})
