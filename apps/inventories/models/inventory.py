from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Inventory(models.Model):
    """
    Inventaire physique d'une boutique
    """

    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('in_progress', 'En cours'),
        ('completed', 'Terminé'),
        ('validated', 'Validé'),
        ('cancelled', 'Annulé'),
    ]

    # Référence
    reference = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Numéro d'inventaire"
    )

    # Boutique
    shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        related_name='inventories',
        verbose_name="Boutique"
    )

    # Dates
    inventory_date = models.DateField(
        verbose_name="Date de l'inventaire",
        help_text="Date du comptage physique"
    )

    # Statut
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Statut"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
        help_text="Observations générales sur l'inventaire"
    )

    # Métadonnées
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de finalisation",
        help_text="Date où l'inventaire a été marqué comme terminé"
    )

    validated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation",
        help_text="Date où l'inventaire a été validé et les stocks ajustés"
    )

    # Utilisateurs
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventories_created',
        verbose_name="Créé par"
    )

    validated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventories_validated',
        verbose_name="Validé par"
    )

    class Meta:
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"
        ordering = ['-inventory_date', '-created_at']
        indexes = [
            models.Index(fields=['shop', 'inventory_date']),
            models.Index(fields=['status']),
            models.Index(fields=['-inventory_date']),
        ]

    def __str__(self):
        return f"{self.reference} - {self.shop.name} ({self.inventory_date})"

    @property
    def total_products(self):
        """Nombre total de produits dans l'inventaire"""
        return self.lines.count()

    @property
    def products_counted(self):
        """Nombre de produits déjà comptés"""
        return self.lines.filter(is_counted=True).count()

    @property
    def counting_progress(self):
        """Pourcentage de progression du comptage"""
        total = self.total_products
        if total == 0:
            return 0
        return round((self.products_counted / total) * 100, 2)

    @property
    def total_discrepancies(self):
        """Nombre total de produits avec écarts"""
        return sum(
            1 for line in self.lines.all()
            if line.difference != 0
        )

    @property
    def total_shortage(self):
        """Quantité totale manquante (écarts négatifs)"""
        return sum(
            line.difference for line in self.lines.all()
            if line.difference < 0
        )

    @property
    def total_surplus(self):
        """Quantité totale en surplus (écarts positifs)"""
        return sum(
            line.difference for line in self.lines.all()
            if line.difference > 0
        )

    @property
    def adjustment_value(self):
        """Valeur totale des ajustements nécessaires"""
        total = 0
        for line in self.lines.all():
            if line.difference != 0:
                total += abs(line.difference) * line.product.cost_price
        return total

    def can_be_validated(self):
        """Vérifie si l'inventaire peut être validé"""
        if self.status != 'completed':
            return False, "L'inventaire doit être terminé avant validation"

        if self.products_counted < self.total_products:
            return False, "Tous les produits doivent être comptés"

        return True, "OK"


class InventoryLine(models.Model):
    """
    Ligne d'inventaire - un produit compté
    """

    # Référence à l'inventaire
    inventory = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name="Inventaire"
    )

    # Produit
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='inventory_lines',
        verbose_name="Produit"
    )

    # Quantités
    expected_quantity = models.IntegerField(
        verbose_name="Quantité attendue",
        help_text="Stock théorique selon le système"
    )

    counted_quantity = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Quantité comptée",
        help_text="Stock réel compté physiquement"
    )

    # Statut
    is_counted = models.BooleanField(
        default=False,
        verbose_name="Compté",
        help_text="Le produit a-t-il été compté?"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
        help_text="Observations sur ce produit"
    )

    # Métadonnées
    counted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de comptage"
    )

    counted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_lines_counted',
        verbose_name="Compté par"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification"
    )

    class Meta:
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"
        ordering = ['product__name']
        unique_together = [['inventory', 'product']]
        indexes = [
            models.Index(fields=['inventory', 'product']),
            models.Index(fields=['is_counted']),
        ]

    def __str__(self):
        return f"{self.inventory.reference} - {self.product.name}"

    @property
    def difference(self):
        """Calcule l'écart entre stock attendu et stock compté"""
        if self.counted_quantity is None:
            return 0
        return self.counted_quantity - self.expected_quantity

    @property
    def difference_percentage(self):
        """Calcule l'écart en pourcentage"""
        if self.expected_quantity == 0:
            if self.counted_quantity == 0:
                return 0
            return 100  # 100% d'écart si on attendait 0 mais trouvé quelque chose

        return round((self.difference / self.expected_quantity) * 100, 2)

    @property
    def discrepancy_status(self):
        """Retourne le statut de l'écart"""
        if not self.is_counted:
            return 'not_counted'

        diff = self.difference
        if diff == 0:
            return 'ok'
        elif diff > 0:
            return 'surplus'
        else:
            return 'shortage'

    @property
    def adjustment_value(self):
        """Valeur de l'ajustement nécessaire"""
        return abs(self.difference) * self.product.cost_price

    def save(self, *args, **kwargs):
        """
        Enregistrer la ligne et marquer comme comptée si quantité fournie
        """
        if self.counted_quantity is not None and not self.is_counted:
            self.is_counted = True
            if not self.counted_at:
                self.counted_at = timezone.now()

        super().save(*args, **kwargs)
