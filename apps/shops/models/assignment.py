from django.db import models
from django.utils import timezone


class ShopAssignment(models.Model):
    """
    Historique des affectations des employés aux boutiques.
    Une ligne = une période d'affectation d'un employé dans une boutique.
    """
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='shop_assignments',
        verbose_name="Employé"
    )
    shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name="Boutique"
    )
    start_date = models.DateField(
        default=timezone.now,
        verbose_name="Date de début"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Affectation en cours"
    )
    assigned_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_made',
        verbose_name="Affecté par"
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Note"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Affectation"
        verbose_name_plural = "Affectations"
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['shop', 'is_active']),
            models.Index(fields=['start_date']),
        ]

    def __str__(self):
        status = "en cours" if self.is_active else f"jusqu'au {self.end_date}"
        return f"{self.user.get_full_name()} → {self.shop.name} ({status})"

    def close(self):
        """Terminer cette affectation."""
        self.is_active = False
        self.end_date = timezone.now().date()
        self.save(update_fields=['is_active', 'end_date'])
