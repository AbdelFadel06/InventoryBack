"""Remplit la grille avec les droits actuels (catalogue). N'écrase jamais une case existante."""
from django.db import migrations


def seed(apps, schema_editor):
    from apps.access.catalog import PERMISSIONS, ROLES

    RolePermission = apps.get_model('access', 'RolePermission')
    RolePermission.objects.bulk_create(
        [
            RolePermission(role=role, code=permission.code, allowed=role in permission.default_roles)
            for permission in PERMISSIONS
            for role in ROLES
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [('access', '0001_permission_tables')]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
