from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Category(models.Model):
    """
    Catégorie de produits
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nom de la catégorie"
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description"
    )

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories',
        verbose_name="Catégorie parente"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def full_path(self):
        """Retourne le chemin complet de la catégorie"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name


class Product(models.Model):
    """
    Produit du système d'inventaire
    """

    # Informations de base
    name = models.CharField(
        max_length=255,
        verbose_name="Nom du produit"
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description"
    )

    # Code produit (SKU - Stock Keeping Unit)
    sku = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Code SKU",
        help_text="Code unique d'identification du produit"
    )

    # Code-barres
    barcode = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        verbose_name="Code-barres"
    )

    # Catégorie
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name="Catégorie"
    )

    # Image
    image = models.ImageField(
        upload_to='product_images/',
        blank=True,
        null=True,
        verbose_name="Image du produit"
    )

    # Prix
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Prix d'achat",
        help_text="Prix d'achat du produit"
    )

    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Prix de vente",
        help_text="Prix de vente du produit"
    )

    # Unité de mesure
    UNIT_CHOICES = [
        ('piece', 'Pièce'),
        ('kg', 'Kilogramme'),
        ('g', 'Gramme'),
        ('l', 'Litre'),
        ('ml', 'Millilitre'),
        ('m', 'Mètre'),
        ('cm', 'Centimètre'),
        ('box', 'Boîte'),
        ('pack', 'Pack'),
        ('other', 'Autre'),
    ]

    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default='piece',
        verbose_name="Unité de mesure"
    )

    # Seuils d'alerte
    minimum_stock = models.PositiveIntegerField(
        default=10,
        verbose_name="Stock minimum",
        help_text="Alerte si stock en-dessous de cette valeur"
    )

    reorder_level = models.PositiveIntegerField(
        default=20,
        verbose_name="Niveau de réapprovisionnement",
        help_text="Niveau recommandé pour commander"
    )

    # Boutique (optionnel - si produit spécifique à une boutique)
    shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='products',
        verbose_name="Boutique",
        help_text="Laisser vide si le produit est commun à toutes les boutiques"
    )

    # Statut
    is_active = models.BooleanField(
        default=True,
        verbose_name="Produit actif"
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

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products_created',
        verbose_name="Créé par"
    )

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ['name']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['barcode']),
            models.Index(fields=['name']),
            models.Index(fields=['category']),
            models.Index(fields=['shop']),
            models.Index(fields=['is_active']),
        ]
        # Un produit peut avoir le même nom dans différentes boutiques
        # mais le SKU doit être unique globalement

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def profit_margin(self):
        """Calcule la marge bénéficiaire en pourcentage"""
        if self.cost_price > 0:
            margin = ((self.selling_price - self.cost_price) / self.cost_price) * 100
            return round(margin, 2)
        return 0

    @property
    def profit_amount(self):
        """Calcule le bénéfice par unité"""
        return self.selling_price - self.cost_price

    def get_current_stock(self, shop=None):
        """
        Retourne le stock actuel du produit
        Si shop est fourni, retourne le stock pour cette boutique
        Sinon, retourne le stock total
        """
        from apps.stocks.models import Stock

        if shop:
            stock = Stock.objects.filter(product=self, shop=shop).first()
            return stock.quantity if stock else 0

        # Stock total toutes boutiques
        total = Stock.objects.filter(product=self).aggregate(
            total=models.Sum('quantity')
        )['total']
        return total or 0

    def is_low_stock(self, shop=None):
        """Vérifie si le stock est bas"""
        current_stock = self.get_current_stock(shop)
        return current_stock < self.minimum_stock

    def needs_reorder(self, shop=None):
        """Vérifie si le produit doit être réapprovisionné"""
        current_stock = self.get_current_stock(shop)
        return current_stock <= self.reorder_level
