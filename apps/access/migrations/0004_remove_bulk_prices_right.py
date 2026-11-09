"""Le changement des prix en masse est mis de côté : ses cases de grille n'ont plus d'objet."""
from django.db import migrations


def remove(apps, schema_editor):
    for model in ('RolePermission', 'UserPermission'):
        apps.get_model('access', model).objects.filter(code='products.bulk_prices').delete()


class Migration(migrations.Migration):

    dependencies = [('access', '0003_module_switches')]

    operations = [migrations.RunPython(remove, migrations.RunPython.noop)]
