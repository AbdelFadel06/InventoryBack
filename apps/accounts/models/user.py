from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


class User(AbstractUser):
    """
    Custom User model pour le système d'inventaire
    """

    GENDER_CHOICES = [
        ('M', 'Masculin'),
        ('F', 'Féminin'),
        ('O', 'Autre'),
    ]

    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Administrateur'),
        ('SHOP_MANAGER', 'Manager de Boutique'),
        ('EMPLOYEE', 'Employé'),
    ]

    # Champs de base
    first_name = models.CharField(max_length=150, verbose_name="Prénom")
    last_name = models.CharField(max_length=150, verbose_name="Nom")
    email = models.EmailField(unique=True, verbose_name="Email")

    # Informations supplémentaires
    phone_number = PhoneNumberField(
        blank=True,
        null=True,
        region='BJ',  # Bénin par défaut (adaptez selon votre pays)
        verbose_name="Numéro de téléphone"
    )

    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
        null=True,
        verbose_name="Sexe"
    )

    date_of_birth = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date de naissance"
    )

    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True,
        verbose_name="Photo de profil"
    )

    # Rôle et boutique
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='EMPLOYEE',
        verbose_name="Rôle"
    )

    shop = models.ForeignKey(
        'shops.Shop',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        verbose_name="Boutique"
    )

    # Métadonnées
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    # Username sera l'email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['shop']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_super_admin(self):
        return self.role == 'SUPER_ADMIN'

    @property
    def is_shop_manager(self):
        return self.role == 'SHOP_MANAGER'

    @property
    def is_employee(self):
        return self.role == 'EMPLOYEE'

    # apps/accounts/models.py

    def save(self, *args, **kwargs):
        # Auto-generate username from email if not provided
        if not self.username:
            self.username = self.email.split('@')[0]

        # SUPER_ADMIN ne doit pas être lié à une boutique
        if self.role == 'SUPER_ADMIN':
            self.shop = None

        super().save(*args, **kwargs)

        # Synchroniser shop.manager si c'est un SHOP_MANAGER
        if self.role == 'SHOP_MANAGER' and self.shop:
            if self.shop.manager != self:
                self.shop.manager = self
                self.shop.save(update_fields=['manager'])
