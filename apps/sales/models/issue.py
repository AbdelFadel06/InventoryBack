from django.db import models


class SaleIssue(models.Model):
    """Problème signalé sur une vente par la caisse, traité ensuite par le manager."""

    REASON_CHOICES = [
        ('wrong_amount',  'Erreur de montant'),
        ('wrong_item',    'Mauvais article'),
        ('client_return', 'Client revenu'),
        ('other',         'Autre'),
    ]
    STATUS_CHOICES = [
        ('open',     'À traiter'),
        ('resolved', 'Traité'),
    ]

    sale = models.ForeignKey(
        'sales.Sale', on_delete=models.CASCADE,
        related_name='issues', verbose_name="Vente"
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, verbose_name="Motif")
    comment = models.TextField(blank=True, default='', verbose_name="Commentaire")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open', verbose_name="Statut")

    reported_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='sale_issues_reported', verbose_name="Signalé par"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    resolved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sale_issues_resolved', verbose_name="Traité par"
    )
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Traité le")
    resolution_note = models.TextField(blank=True, default='', verbose_name="Note de traitement")

    class Meta:
        verbose_name = "Signalement de vente"
        verbose_name_plural = "Signalements de vente"
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f"{self.sale.reference} — {self.get_reason_display()}"
