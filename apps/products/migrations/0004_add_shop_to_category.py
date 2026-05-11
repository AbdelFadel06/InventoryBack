from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_remove_product_cost_price'),
        ('shops', '0004_backfill_managers_m2m'),
    ]

    operations = [
        # Supprimer l'ancienne contrainte unique sur name seul
        migrations.AlterField(
            model_name='category',
            name='name',
            field=models.CharField(max_length=100, verbose_name='Nom de la catégorie'),
        ),
        # Ajouter le FK shop
        migrations.AddField(
            model_name='category',
            name='shop',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='categories',
                to='shops.shop',
                verbose_name='Boutique',
            ),
        ),
        # Backfill : toutes les catégories existantes appartiennent à la boutique 1
        migrations.RunSQL(
            "UPDATE products_category SET shop_id = 1 WHERE shop_id IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Contrainte unique par (boutique, nom)
        migrations.AlterUniqueTogether(
            name='category',
            unique_together={('shop', 'name')},
        ),
    ]
