from django.db import models

ROLE_CHOICES = [
    ('SUPER_ADMIN',  'Super Administrateur'),
    ('SHOP_MANAGER', 'Manager de Boutique'),
    ('EMPLOYEE',     'Employé'),
    ('LIVREUR',      'Livreur'),
    ('MAGASINIER',   'Magasinier'),
]


class RolePermission(models.Model):
    """Une case de la grille : ce rôle a-t-il ce droit ? Mêmes droits dans toutes les boutiques."""
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    code = models.CharField(max_length=60)
    allowed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Droit d'un rôle"
        verbose_name_plural = "Droits des rôles"
        constraints = [models.UniqueConstraint(fields=['role', 'code'], name='unique_role_permission')]

    def __str__(self):
        return f"{self.role} · {self.code} = {'oui' if self.allowed else 'non'}"


class UserPermission(models.Model):
    """Exception pour une personne : ajoute (allowed=True) ou retire (False) un droit de son rôle."""
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='permission_overrides')
    code = models.CharField(max_length=60)
    allowed = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Exception de droit"
        verbose_name_plural = "Exceptions de droits"
        constraints = [models.UniqueConstraint(fields=['user', 'code'], name='unique_user_permission')]

    def __str__(self):
        return f"{self.user} · {self.code} = {'ajouté' if self.allowed else 'retiré'}"


class PermissionChange(models.Model):
    """Journal : qui a changé quel droit, pour quel rôle ou quelle personne, et quand."""
    changed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='+')
    role = models.CharField(max_length=20, blank=True, default='')
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    code = models.CharField(max_length=60)
    before = models.BooleanField(null=True)   # null : pas d'exception avant
    after = models.BooleanField(null=True)    # null : exception retirée
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Changement de droit"
        verbose_name_plural = "Journal des droits"
        ordering = ['-created_at']


class ModuleSwitch(models.Model):
    """Interrupteur d'un module : la grille décide (True) ou les anciennes règles (False)."""
    module = models.CharField(max_length=30, unique=True)
    enabled = models.BooleanField(default=False)
    updated_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Interrupteur de module"
        verbose_name_plural = "Interrupteurs de modules"

    def __str__(self):
        return f"{self.module} : {'grille' if self.enabled else 'anciennes règles'}"
