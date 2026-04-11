"""
ActiveShopMixin — résout la boutique effective pour les managers multi-boutiques.

Le frontend envoie le header X-Active-Shop: <shop_id> quand le manager
a sélectionné une boutique différente de sa boutique par défaut.
Le mixin vérifie que le manager gère bien cette boutique avant d'accepter.
"""
from apps.shops.models import Shop


class ActiveShopMixin:
    """
    Mixin à ajouter aux ViewSets qui filtrent par user.shop.
    Expose self.get_active_shop(request) qui retourne la boutique effective.
    """

    def get_active_shop(self, request):
        user = request.user

        if not user.is_authenticated:
            return None

        # Super admin : pas de boutique active
        if user.role == 'SUPER_ADMIN':
            return None

        # Lire le header X-Active-Shop
        shop_id = request.headers.get('X-Active-Shop')
        if shop_id:
            try:
                shop_id = int(shop_id)
                # Vérifier que le manager gère bien cette boutique
                if user.role == 'SHOP_MANAGER':
                    if user.managed_shops.filter(id=shop_id).exists():
                        return Shop.objects.get(id=shop_id)
                elif user.shop_id == shop_id:
                    return user.shop
            except (ValueError, Shop.DoesNotExist):
                pass

        # Fallback : boutique courante de l'utilisateur
        return user.shop
