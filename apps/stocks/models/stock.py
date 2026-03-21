from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Stock(models.Model):
    """
    Stock actuel d'un produit dans une boutique
    """
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name="Produit"
    )

    shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name="Boutique"
    )

    quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Quantité en stock"
    )

    # Métadonnées
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière mise à jour"
    )

    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_updates',
        verbose_name="Mis à jour par"
    )

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        ordering = ['shop', 'product']
        # Un produit ne peut avoir qu'un seul stock par boutique
        unique_together = [['product', 'shop']]
        indexes = [
            models.Index(fields=['product', 'shop']),
            models.Index(fields=['shop']),
            models.Index(fields=['quantity']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.shop.name}: {self.quantity} {self.product.unit}"

    @property
    def is_low_stock(self):
        """Vérifie si le stock est bas"""
        return self.quantity < self.product.minimum_stock

    @property
    def needs_reorder(self):
        """Vérifie si le produit doit être réapprovisionné"""
        return self.quantity <= self.product.reorder_level

    @property
    def stock_status(self):
        """Retourne le statut du stock"""
        if self.quantity == 0:
            return 'out_of_stock'
        elif self.quantity < self.product.minimum_stock:
            return 'critical'
        elif self.quantity <= self.product.reorder_level:
            return 'low'
        return 'ok'

    @property
    def stock_value(self):
        """Calcule la valeur du stock (quantité × prix d'achat)"""
        return self.quantity * self.product.cost_price


class StockMovement(models.Model):
    """
    Historique des mouvements de stock
    """

    MOVEMENT_TYPES = [
        ('entry', 'Entrée (Réception)'),
        ('exit', 'Sortie (Vente)'),
        ('transfer_out', 'Transfert sortant'),
        ('transfer_in', 'Transfert entrant'),
        ('adjustment', 'Ajustement manuel'),
        ('return', 'Retour'),
        ('damage', 'Casse/Perte'),
        ('inventory', 'Ajustement inventaire'),
    ]

    # Référence
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='movements',
        verbose_name="Produit"
    )

    shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        related_name='stock_movements',
        verbose_name="Boutique"
    )

    # Type et quantité
    movement_type = models.CharField(
        max_length=20,
        choices=MOVEMENT_TYPES,
        verbose_name="Type de mouvement"
    )

    quantity = models.IntegerField(
        verbose_name="Quantité",
        help_text="Positif pour ajout, négatif pour retrait"
    )

    quantity_before = models.IntegerField(
        verbose_name="Quantité avant",
        help_text="Stock avant ce mouvement"
    )

    quantity_after = models.IntegerField(
        verbose_name="Quantité après",
        help_text="Stock après ce mouvement"
    )

    # Transfert (si applicable)
    related_shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='related_movements',
        verbose_name="Boutique liée",
        help_text="Pour les transferts: boutique source ou destination"
    )

    # Informations supplémentaires
    reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Référence",
        help_text="Numéro de commande, bon de livraison, etc."
    )

    reason = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motif",
        help_text="Raison du mouvement"
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes"
    )

    # Prix unitaire au moment du mouvement
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix unitaire",
        help_text="Prix d'achat ou de vente au moment du mouvement"
    )

    # Métadonnées
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date du mouvement"
    )

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements_created',
        verbose_name="Créé par"
    )

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', 'shop']),
            models.Index(fields=['shop', 'created_at']),
            models.Index(fields=['movement_type']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        sign = '+' if self.quantity > 0 else ''
        return f"{self.get_movement_type_display()} - {self.product.name}: {sign}{self.quantity} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def total_value(self):
        """Calcule la valeur totale du mouvement"""
        if self.unit_price:
            return abs(self.quantity) * self.unit_price
        return abs(self.quantity) * self.product.cost_price

    def save(self, *args, **kwargs):
        """
        Enregistrer le mouvement et mettre à jour le stock
        """
        # Si c'est une nouvelle création (pas une mise à jour)
        if not self.pk:
            # Récupérer ou créer le stock
            stock, created = Stock.objects.get_or_create(
                product=self.product,
                shop=self.shop,
                defaults={'quantity': 0}
            )

            # Enregistrer la quantité avant
            self.quantity_before = stock.quantity

            # Calculer la nouvelle quantité
            new_quantity = stock.quantity + self.quantity

            # Vérifier que la quantité ne devient pas négative
            if new_quantity < 0:
                from django.core.exceptions import ValidationError
                raise ValidationError(
                    f"Stock insuffisant. Stock actuel: {stock.quantity}, "
                    f"tentative de retrait: {abs(self.quantity)}"
                )

            # Mettre à jour le stock
            stock.quantity = new_quantity
            stock.updated_by = self.created_by
            stock.save()

            # Enregistrer la quantité après
            self.quantity_after = new_quantity

        super().save(*args, **kwargs)


class StockTransfer(models.Model):
    """
    Transfert de stock entre boutiques
    """

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('in_transit', 'En transit'),
        ('received', 'Reçu'),
        ('cancelled', 'Annulé'),
    ]

    # Référence
    reference = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Numéro de transfert"
    )

    # Boutiques
    from_shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        related_name='transfers_out',
        verbose_name="Boutique source"
    )

    to_shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        related_name='transfers_in',
        verbose_name="Boutique destination"
    )

    # Produit et quantité
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='transfers',
        verbose_name="Produit"
    )

    quantity = models.PositiveIntegerField(
        verbose_name="Quantité"
    )

    # Statut
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Statut"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes"
    )

    # Métadonnées
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'envoi"
    )

    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de réception"
    )

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='transfers_created',
        verbose_name="Créé par"
    )

    received_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfers_received',
        verbose_name="Reçu par"
    )

    class Meta:
        verbose_name = "Transfert de stock"
        verbose_name_plural = "Transferts de stock"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['from_shop', 'to_shop']),
            models.Index(fields=['status']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.reference} - {self.product.name}: {self.from_shop.name} → {self.to_shop.name}"
