from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(max_length=500, verbose_name='URL Cloudinary')),
                ('is_primary', models.BooleanField(default=False, verbose_name='Image principale')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name="Ordre d'affichage")),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='images',
                    to='products.product',
                    verbose_name='Produit'
                )),
            ],
            options={
                'verbose_name': 'Image produit',
                'verbose_name_plural': 'Images produit',
                'ordering': ['order', 'created_at'],
            },
        ),
    ]
