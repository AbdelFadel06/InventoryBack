from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_add_client_phone_and_livreur_paid'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='order_discount',
            field=models.DecimalField(
                max_digits=12, decimal_places=2,
                default=Decimal('0.00'),
            ),
        ),
    ]
