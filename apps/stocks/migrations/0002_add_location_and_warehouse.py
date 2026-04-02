from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stocks', '0001_initial'),
    ]

    operations = [
        # ── 1. Stock: remove old unique_together ──────────────────────
        migrations.AlterUniqueTogether(
            name='stock',
            unique_together=set(),
        ),

        # ── 2. Stock: add location field ──────────────────────────────
        migrations.AddField(
            model_name='stock',
            name='location',
            field=models.CharField(
                choices=[('BOUTIQUE', 'Boutique'), ('MAGASIN', 'Magasin')],
                default='BOUTIQUE',
                max_length=10,
                verbose_name='Emplacement',
            ),
        ),

        # ── 3. Stock: add new unique_together (product, shop, location)
        migrations.AlterUniqueTogether(
            name='stock',
            unique_together={('product', 'shop', 'location')},
        ),

        # ── 4. Stock: update index ─────────────────────────────────────
        migrations.AlterIndexTogether(
            name='stock',
            index_together=set(),
        ),

        # ── 5. StockMovement: add location field ──────────────────────
        migrations.AddField(
            model_name='stockmovement',
            name='location',
            field=models.CharField(
                choices=[('BOUTIQUE', 'Boutique'), ('MAGASIN', 'Magasin')],
                default='BOUTIQUE',
                max_length=10,
                verbose_name='Emplacement',
            ),
        ),

        # ── 6. StockTransfer: add transfer_type field ─────────────────
        migrations.AddField(
            model_name='stocktransfer',
            name='transfer_type',
            field=models.CharField(
                choices=[
                    ('inter_shop', 'Inter-boutique'),
                    ('warehouse',  'Magasin → Boutique'),
                ],
                default='inter_shop',
                max_length=20,
                verbose_name='Type de transfert',
            ),
        ),
    ]
