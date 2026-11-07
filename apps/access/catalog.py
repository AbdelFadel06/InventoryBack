"""
Catalogue des droits de ShopM : chaque action qu'un rôle peut faire, rangée par module.

Les valeurs par défaut reproduisent EXACTEMENT le comportement actuel de l'API (grille
de apps/accounts/test_permissions_baseline.py, vérifiée par apps/access/tests.py).
Les cases ne règlent que les actions : ce que chacun voit (sa boutique, le livreur et
ses seules livraisons, le caissier de la session du jour) reste décidé dans le code.

Ajouter un droit : l'ajouter ici, puis une migration de données pour ses lignes.
"""
from dataclasses import dataclass

ADMIN = 'SUPER_ADMIN'
MANAGER = 'SHOP_MANAGER'
EMPLOYEE = 'EMPLOYEE'
LIVREUR = 'LIVREUR'
MAGASINIER = 'MAGASINIER'
ROLES = (ADMIN, MANAGER, EMPLOYEE, MAGASINIER, LIVREUR)

ALL = set(ROLES)
ADMIN_ONLY = {ADMIN}
ADMIN_MANAGER = {ADMIN, MANAGER}
STOCK_WRITERS = {ADMIN, MANAGER, MAGASINIER}
NOT_WAREHOUSE = {ADMIN, MANAGER, EMPLOYEE, LIVREUR}
BOUTIQUE_FIGURES = {ADMIN, MANAGER, EMPLOYEE}
REGISTER = {MANAGER, EMPLOYEE}   # caissier de la session du jour (contrôlé dans le code) et manager

# Colonnes de la grille à l'écran.
VIEW, CREATE, UPDATE, DELETE, SPECIAL = 'view', 'create', 'update', 'delete', 'special'

# Droit verrouillé : le Super Admin le garde toujours, pour ne jamais se bloquer.
MANAGE_PERMISSIONS = 'permissions.manage'


@dataclass(frozen=True)
class Permission:
    code: str
    module: str
    label: str
    kind: str
    default_roles: frozenset


def _p(code, module, label, kind, roles):
    return Permission(code, module, label, kind, frozenset(roles))


PERMISSIONS = [
    # ── Utilisateurs ──────────────────────────────────────────────
    _p('users.view',          'Utilisateurs', "Voir les comptes",                VIEW,    ALL),
    _p('users.create',        'Utilisateurs', "Créer un compte",                 CREATE,  ADMIN_MANAGER),
    _p('users.update',        'Utilisateurs', "Modifier un compte",              UPDATE,  ADMIN_MANAGER),
    _p('users.delete',        'Utilisateurs', "Supprimer un compte",             DELETE,  ADMIN_MANAGER),
    _p('users.toggle_active', 'Utilisateurs', "Activer / désactiver un compte",  SPECIAL, ADMIN_MANAGER),

    # ── Boutiques ─────────────────────────────────────────────────
    _p('shops.view',           'Boutiques', "Voir les boutiques",              VIEW,    ALL),
    _p('shops.create',         'Boutiques', "Créer une boutique",              CREATE,  ADMIN_ONLY),
    _p('shops.update',         'Boutiques', "Modifier une boutique",           UPDATE,  ADMIN_ONLY),
    _p('shops.delete',         'Boutiques', "Supprimer une boutique",          DELETE,  ADMIN_ONLY),
    _p('shops.assign_manager', 'Boutiques', "Affecter un manager",             SPECIAL, ADMIN_ONLY),
    _p('shops.assign_staff',   'Boutiques', "Affecter des employés",           SPECIAL, ADMIN_MANAGER),

    # ── Produits ──────────────────────────────────────────────────
    _p('products.view',        'Produits', "Voir les produits",                VIEW,    ALL),
    _p('products.create',      'Produits', "Créer un produit",                 CREATE,  ADMIN_MANAGER),
    _p('products.update',      'Produits', "Modifier un produit",              UPDATE,  ADMIN_MANAGER),
    _p('products.delete',      'Produits', "Supprimer un produit",             DELETE,  ADMIN_MANAGER),
    _p('products.bulk_prices', 'Produits', "Changer les prix en masse",        SPECIAL, ADMIN_ONLY),
    _p('categories.manage',    'Produits', "Gérer les catégories",             SPECIAL, ADMIN_MANAGER),

    # ── Stock ─────────────────────────────────────────────────────
    _p('stock.view',             'Stock', "Voir le stock",                     VIEW,    ALL),
    _p('stock.adjust_warehouse', 'Stock', "Ajuster le stock du magasin",       UPDATE,  STOCK_WRITERS),
    _p('stock.adjust_boutique',  'Stock', "Ajuster le stock de la boutique",   SPECIAL, ADMIN_MANAGER),
    _p('stock.movements',        'Stock', "Entrées et sorties de stock",       CREATE,  STOCK_WRITERS),
    _p('transfers.create',       'Stock', "Créer et envoyer un transfert",     SPECIAL, STOCK_WRITERS),

    # ── Inventaires ───────────────────────────────────────────────
    _p('inventories.view',     'Inventaires', "Voir les inventaires",                 VIEW,    ALL),
    _p('inventories.create',   'Inventaires', "Créer un inventaire",                  CREATE,  ADMIN_MANAGER),
    _p('inventories.count',    'Inventaires', "Compter les produits",                 UPDATE,  ALL),
    _p('inventories.cancel',   'Inventaires', "Annuler ou supprimer un inventaire",   DELETE,  ADMIN_MANAGER),
    _p('inventories.validate', 'Inventaires', "Terminer et valider un inventaire",    SPECIAL, ADMIN_MANAGER),

    # ── Caisse et ventes ──────────────────────────────────────────
    _p('sales.view',         'Ventes', "Voir les ventes",                            VIEW,    NOT_WAREHOUSE),
    _p('sales.create',       'Ventes', "Encaisser une vente",                        CREATE,  REGISTER),
    _p('sales.report_issue', 'Ventes', "Signaler une vente",                         SPECIAL, REGISTER),
    _p('sales.cancel',       'Ventes', "Annuler une vente (avec motif)",             DELETE,  ADMIN_MANAGER),
    _p('sales.correct',      'Ventes', "Corriger une vente",                         UPDATE,  ADMIN_MANAGER),
    _p('reports.view',       'Ventes', "Voir les rapports et chiffres de boutique",  SPECIAL, BOUTIQUE_FIGURES),

    # ── Livraisons ────────────────────────────────────────────────
    _p('deliveries.modify',           'Livraisons', "Modifier une livraison",             UPDATE,  {ADMIN, MANAGER, EMPLOYEE}),
    _p('deliveries.mark_delivered',   'Livraisons', "Confirmer ses livraisons",           SPECIAL, {LIVREUR}),
    _p('deliveries.validate_payment', 'Livraisons', "Valider l'argent d'un livreur",      SPECIAL, REGISTER),
    _p('deliveries.pay_livreur',      'Livraisons', "Payer la commission du livreur",     SPECIAL, ADMIN_MANAGER),

    # ── Sessions de caisse et dépenses ────────────────────────────
    _p('sessions.view',   'Caisse', "Voir les sessions de caisse",               VIEW,    BOUTIQUE_FIGURES),
    _p('sessions.manage', 'Caisse', "Ouvrir, clôturer ou supprimer une session", SPECIAL, ADMIN_MANAGER),
    _p('expenses.view',   'Caisse', "Voir les dépenses",                         VIEW,    BOUTIQUE_FIGURES),
    _p('expenses.create', 'Caisse', "Saisir une dépense",                        CREATE,  REGISTER),
    _p('expenses.delete', 'Caisse', "Supprimer une dépense",                     DELETE,  ADMIN_MANAGER),

    # ── Notifications et administration ───────────────────────────
    _p('notifications.receive', 'Administration', "Recevoir les notifications",   SPECIAL, {MANAGER}),
    _p(MANAGE_PERMISSIONS,      'Administration', "Gérer les permissions",        SPECIAL, ADMIN_ONLY),
]

BY_CODE = {p.code: p for p in PERMISSIONS}
assert len(BY_CODE) == len(PERMISSIONS), "code de permission en double"


def default_allowed(role, code):
    permission = BY_CODE.get(code)
    return bool(permission and role in permission.default_roles)
