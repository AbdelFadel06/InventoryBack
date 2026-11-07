"""
Notifications sur téléphone (Web Push), réservées aux managers de la boutique concernée.

L'envoi part après l'enregistrement en base, dans un fil séparé : une vente ou un
mouvement de stock n'attend jamais le téléphone, et un échec d'envoi ne casse rien.
Sans clés VAPID dans le .env, rien n'est envoyé.
"""
import json
import logging
import threading

from django.conf import settings
from django.db import connection, transaction

logger = logging.getLogger(__name__)


def is_configured():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def notify_shop_managers(shop, title, body, url, tag=None):
    if not is_configured():
        return
    shop_id = shop.id if hasattr(shop, 'id') else shop
    payload = json.dumps({'title': title, 'body': body, 'url': url, 'tag': tag, 'shop': shop_id})
    transaction.on_commit(lambda: _dispatch(shop_id, payload))


def notify_user(user, title, body, url):
    """Notification d'essai, vers les appareils d'un seul utilisateur."""
    if not is_configured():
        return 0
    subscriptions = list(user.push_subscriptions.all())
    payload = json.dumps({'title': title, 'body': body, 'url': url, 'tag': 'test'})
    run_in_background(_send_all, subscriptions, payload)
    return len(subscriptions)


def _dispatch(shop_id, payload):
    from .models import PushSubscription
    subscriptions = list(PushSubscription.objects.filter(
        user__managed_shops__id=shop_id, user__role='SHOP_MANAGER', user__is_active=True,
    ).distinct())
    if subscriptions:
        run_in_background(_send_all, subscriptions, payload)


def run_in_background(function, *args):
    def target():
        try:
            function(*args)
        finally:
            # Le fil a sa propre connexion à la base : la rendre.
            connection.close()
    threading.Thread(target=target, daemon=True).start()


def _send_all(subscriptions, payload):
    from pywebpush import WebPushException, webpush
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_SUBJECT},
                ttl=12 * 3600,
                timeout=10,
            )
        except WebPushException as exc:
            status = getattr(exc.response, 'status_code', None)
            if status in (404, 410):
                # Le téléphone s'est désabonné ou l'appli a été désinstallée.
                subscription.delete()
            else:
                logger.warning("Notification non envoyée (%s) : %s", status, exc)
        except Exception:
            logger.exception("Notification non envoyée")
