from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.core.validators import RegexValidator


class Shop(models.Model):
    """
    Model pour les boutiques/magasins
    """

    # Informations de base
    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom de la boutique"
    )

    slogan = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Slogan"
    )

    logo = models.ImageField(
        upload_to='shop_logos/',
        blank=True,
        null=True,
        verbose_name="Logo"
    )

    # Informations fiscales
    ifu = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name="IFU (Identifiant Fiscal Unique)",
        help_text="Numéro d'identification fiscale"
    )

    # Contact
    phone_number = PhoneNumberField(
        blank=True,
        null=True,
        region='BJ',
        verbose_name="Numéro de téléphone"
    )

    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email de contact"
    )

    # Adresse
    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="Adresse"
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Ville"
    )

    country = models.CharField(
        max_length=100,
        default="Bénin",
        verbose_name="Pays"
    )

    # Manager principal
    manager = models.OneToOneField(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_shop',
        limit_choices_to={'role': 'SHOP_MANAGER'},
        verbose_name="Manager principal"
    )

    # Statut
    is_active = models.BooleanField(
        default=True,
        verbose_name="Boutique active"
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
        related_name='shops_created',
        verbose_name="Créé par"
    )

    class Meta:
        verbose_name = "Boutique"
        verbose_name_plural = "Boutiques"
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['manager']),
        ]

    def __str__(self):
        return self.name

    @property
    def total_employees(self):
        """Nombre total d'employés (manager + employees)"""
        return self.users.filter(is_active=True).count()

    @property
    def active_employees(self):
        """Nombre d'employés actifs (sans le manager)"""
        return self.users.filter(
            is_active=True,
            role='EMPLOYEE'
        ).count()

    def get_employees(self):
        """Retourne tous les employés de la boutique"""
        return self.users.filter(role='EMPLOYEE')

    def get_all_staff(self):
        """Retourne tous les employés incluant le manager"""
        return self.users.filter(is_active=True)
