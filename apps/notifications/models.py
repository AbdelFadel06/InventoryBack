from django.db import models


class PushSubscription(models.Model):
    """Un téléphone (ou navigateur) d'un manager abonné aux notifications."""

    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='push_subscriptions', verbose_name="Utilisateur"
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Abonnement aux notifications"
        verbose_name_plural = "Abonnements aux notifications"

    def __str__(self):
        return f"{self.user} — {self.user_agent[:40]}"
