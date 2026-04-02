from django.db import migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_phone_number_to_charfield'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=__import__('django.db.models', fromlist=['CharField']).CharField(
                choices=[
                    ('SUPER_ADMIN',  'Super Administrateur'),
                    ('SHOP_MANAGER', 'Manager de Boutique'),
                    ('EMPLOYEE',     'Employé'),
                    ('LIVREUR',      'Livreur'),
                    ('MAGASINIER',   'Magasinier'),
                ],
                default='EMPLOYEE',
                max_length=20,
                verbose_name='Rôle',
            ),
        ),
    ]
