"""
Droits effectifs d'un utilisateur : exception personnelle, sinon case de son rôle,
sinon valeur par défaut du catalogue. Rien n'utilise encore ce calcul pour autoriser
ou refuser (étapes 4-5 : comparaison en parallèle, puis bascule module par module).
"""
from .catalog import ADMIN, BY_CODE, MANAGE_PERMISSIONS, PERMISSIONS, default_allowed

_CACHE_ATTR = '_shopm_permissions'


def effective_permissions(user):
    """{code: bool} pour tout le catalogue. Calculé une fois par requête (mis en cache sur l'objet user)."""
    cached = getattr(user, _CACHE_ATTR, None)
    if cached is not None:
        return cached

    from .models import RolePermission, UserPermission

    if not (user and user.is_authenticated and user.is_active):
        result = {p.code: False for p in PERMISSIONS}
    else:
        by_role = dict(RolePermission.objects.filter(role=user.role).values_list('code', 'allowed'))
        overrides = dict(UserPermission.objects.filter(user=user).values_list('code', 'allowed'))
        result = {}
        for permission in PERMISSIONS:
            code = permission.code
            if code in overrides:
                result[code] = overrides[code]
            elif code in by_role:
                result[code] = by_role[code]
            else:
                result[code] = default_allowed(user.role, code)
        if user.role == ADMIN:
            result[MANAGE_PERMISSIONS] = True   # verrouillé : jamais de blocage du Super Admin

    try:
        setattr(user, _CACHE_ATTR, result)
    except AttributeError:
        pass
    return result


def forget_permissions(user):
    """Vide le cache par requête (après un changement de droits dans la même requête)."""
    if hasattr(user, _CACHE_ATTR):
        delattr(user, _CACHE_ATTR)


def has_perm(user, code):
    if code not in BY_CODE:
        raise KeyError(f"Droit inconnu : {code}")
    return effective_permissions(user)[code]
