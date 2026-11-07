from django.urls import path

from .views import PushKeyView, PushSubscribeView, PushTestView, PushUnsubscribeView

urlpatterns = [
    path('notifications/push/key/',         PushKeyView.as_view(),         name='push-key'),
    path('notifications/push/subscribe/',   PushSubscribeView.as_view(),   name='push-subscribe'),
    path('notifications/push/unsubscribe/', PushUnsubscribeView.as_view(), name='push-unsubscribe'),
    path('notifications/push/test/',        PushTestView.as_view(),        name='push-test'),
]
