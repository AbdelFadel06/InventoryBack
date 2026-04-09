from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0002_productimage'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='cost_price',
        ),
    ]
