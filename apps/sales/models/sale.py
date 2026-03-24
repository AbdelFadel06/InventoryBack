# apps/sales/models/sale.py
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class CashierSession(models.Model):
    """
    Session de caisse — le manager désigne un caissier pour une période
    """
    PERIOD_CHOICES = [
        ('daily',  'Journalière'),
        ('weekly', 'Hebdomadaire'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Clôturée'),
    ]

    shop = models.ForeignKey(
        'shops.Shop', on_delete=models.CASCADE,
        related_name='cashier_sessions', verbose_name="Boutique"
    )
    cashier = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='cashier_sessions', verbose_name="Caissier"
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='sessions_created', verbose_name="Créé par"
    )
    period_type = models.CharField(
        max_length=10, choices=PERIOD_CHOICES,
        default='daily', verbose_name="Type de période"
    )
    start_date = models.DateField(verbose_name="Date de début")
    end_date   = models.DateField(verbose_name="Date de fin")
    status     = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default='active', verbose_name="Statut"
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Session de caisse"
        verbose_name_plural = "Sessions de caisse"
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['shop', 'status']),
            models.Index(fields=['cashier', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        return f"{self.shop.name} — {self.cashier.get_full_name()} ({self.start_date})"

    @property
    def is_active(self):
        from django.utils import timezone
        today = timezone.now().date()
        return (
            self.status == 'active' and
            self.start_date <= today <= self.end_date
        )


class Sale(models.Model):
    """
    Vente enregistrée par le caissier
    """
    SALE_TYPE_CHOICES = [
        ('direct',   'Vente directe'),
        ('delivery', 'Livraison'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('cash',         'Espèces'),
        ('mobile_money', 'Mobile Money'),
        ('on_delivery',  'Paiement à la livraison'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('paid',    'Payé'),
        ('pending', 'En attente'),
    ]
    STATUS_CHOICES = [
        ('completed', 'Complétée'),
        ('cancelled', 'Annulée'),
    ]

    reference = models.CharField(
        max_length=50, unique=True, verbose_name="Référence"
    )
    session = models.ForeignKey(
        CashierSession, on_delete=models.CASCADE,
        related_name='sales', verbose_name="Session de caisse"
    )
    shop = models.ForeignKey(
        'shops.Shop', on_delete=models.CASCADE,
        related_name='sales', verbose_name="Boutique"
    )
    cashier = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='sales_as_cashier', verbose_name="Caissier"
    )

    # Type de vente
    sale_type = models.CharField(
        max_length=10, choices=SALE_TYPE_CHOICES,
        default='direct', verbose_name="Type de vente"
    )

    # Paiement
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES,
        default='cash', verbose_name="Moyen de paiement"
    )
    payment_status = models.CharField(
        max_length=10, choices=PAYMENT_STATUS_CHOICES,
        default='paid', verbose_name="Statut paiement"
    )

    # Livraison (si sale_type = delivery)
    livreur = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deliveries', verbose_name="Livreur"
    )
    delivery_address = models.TextField(
        blank=True, null=True, verbose_name="Adresse de livraison"
    )
    delivered_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Livré le"
    )

    # Montants
    subtotal       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Statut
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES,
        default='completed', verbose_name="Statut"
    )

    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vente"
        verbose_name_plural = "Ventes"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shop', 'created_at']),
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['livreur', 'payment_status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.reference} — {self.total_amount} F ({self.get_sale_type_display()})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"VTE-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def recalculate_totals(self):
        subtotal = sum(item.subtotal for item in self.items.all())
        discount = sum(item.discount_amount for item in self.items.all())
        self.subtotal       = subtotal
        self.total_discount = discount
        self.total_amount   = subtotal - discount
        self.save(update_fields=['subtotal', 'total_discount', 'total_amount'])


class SaleItem(models.Model):
    """
    Ligne d'une vente — un produit
    """
    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE,
        related_name='items', verbose_name="Vente"
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='sale_items', verbose_name="Produit"
    )
    quantity   = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Réduction
    discount_type   = models.CharField(
        max_length=10,
        choices=[('fixed', 'Montant fixe'), ('percent', 'Pourcentage')],
        blank=True, null=True
    )
    discount_value  = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('0.00')
    )
    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal('0.00')
    )

    subtotal    = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de vente"
        verbose_name_plural = "Lignes de vente"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.product.selling_price

        self.subtotal = self.unit_price * self.quantity

        # Calcul réduction
        if self.discount_type == 'percent' and self.discount_value:
            self.discount_amount = (self.subtotal * self.discount_value / 100).quantize(Decimal('0.01'))
        elif self.discount_type == 'fixed' and self.discount_value:
            self.discount_amount = min(self.discount_value, self.subtotal)
        else:
            self.discount_amount = Decimal('0.00')

        self.total_price = self.subtotal - self.discount_amount
        super().save(*args, **kwargs)


class Expense(models.Model):
    """
    Dépense journalière saisie par le caissier
    """
    session    = models.ForeignKey(
        CashierSession, on_delete=models.CASCADE,
        related_name='expenses', verbose_name="Session"
    )
    shop       = models.ForeignKey(
        'shops.Shop', on_delete=models.CASCADE,
        related_name='expenses'
    )
    label      = models.CharField(max_length=200, verbose_name="Libellé")
    amount     = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant"
    )
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='expenses_created'
    )
    sale_date  = models.DateField(verbose_name="Date")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shop', 'sale_date']),
            models.Index(fields=['session']),
        ]

    def __str__(self):
        return f"{self.label} — {self.amount} F"
