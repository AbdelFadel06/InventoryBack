from rest_framework import serializers
from apps.shops.models import Shop
from apps.accounts.serializers import UserListSerializer


class ShopSerializer(serializers.ModelSerializer):
    """
    Serializer complet pour les boutiques
    """
    manager_name = serializers.CharField(
        source='manager.get_full_name',
        read_only=True,
        allow_null=True
    )
    manager_email = serializers.EmailField(
        source='manager.email',
        read_only=True,
        allow_null=True
    )
    total_employees = serializers.IntegerField(read_only=True)
    active_employees = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'slogan', 'logo', 'ifu',
            'phone_number', 'email', 'address', 'city', 'country',
            'manager', 'manager_name', 'manager_email',
            'is_active', 'total_employees', 'active_employees',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def validate_manager(self, value):
        """Valider que le manager a bien le rôle SHOP_MANAGER"""
        if value and value.role != 'SHOP_MANAGER':
            raise serializers.ValidationError(
                "L'utilisateur sélectionné n'est pas un manager de boutique."
            )
        return value

    def validate_logo(self, value):
        """Valider la taille du logo (max 5MB)"""
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "La taille du logo ne doit pas dépasser 5MB."
            )
        return value

    def validate_ifu(self, value):
        """Valider le format de l'IFU (optionnel mais si fourni, doit être valide)"""
        if value:
            # Retirer les espaces
            value = value.strip()
            # Vérifier que ce n'est pas vide après strip
            if not value:
                return None
        return value


class ShopCreateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la création de boutiques
    """
    class Meta:
        model = Shop
        fields = [
            'name', 'slogan', 'logo', 'ifu',
            'phone_number', 'email', 'address', 'city', 'country',
            'manager'
        ]

    def validate_manager(self, value):
        """Valider que le manager a bien le rôle SHOP_MANAGER"""
        if value and value.role != 'SHOP_MANAGER':
            raise serializers.ValidationError(
                "L'utilisateur sélectionné n'est pas un manager de boutique."
            )

        # Vérifier que le manager n'est pas déjà assigné à une autre boutique
        if value and hasattr(value, 'managed_shop') and value.managed_shop:
            raise serializers.ValidationError(
                f"{value.get_full_name()} gère déjà la boutique '{value.managed_shop.name}'."
            )

        return value

    def create(self, validated_data):
        # Ajouter l'utilisateur qui crée la boutique
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        shop = Shop.objects.create(**validated_data)

        # Si un manager est assigné, mettre à jour sa boutique
        if shop.manager:
            shop.manager.shop = shop
            shop.manager.save()

        return shop


class ShopUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la mise à jour de boutiques
    """
    class Meta:
        model = Shop
        fields = [
            'name', 'slogan', 'logo', 'ifu',
            'phone_number', 'email', 'address', 'city', 'country',
            'manager', 'is_active'
        ]

    def validate_manager(self, value):
        """Valider que le manager a bien le rôle SHOP_MANAGER"""
        if value and value.role != 'SHOP_MANAGER':
            raise serializers.ValidationError(
                "L'utilisateur sélectionné n'est pas un manager de boutique."
            )

        # Vérifier que le manager n'est pas déjà assigné à une autre boutique
        # (sauf s'il s'agit de la boutique actuelle)
        if value and hasattr(value, 'managed_shop') and value.managed_shop:
            if value.managed_shop.id != self.instance.id:
                raise serializers.ValidationError(
                    f"{value.get_full_name()} gère déjà la boutique '{value.managed_shop.name}'."
                )

        return value

    def update(self, instance, validated_data):
        old_manager = instance.manager
        new_manager = validated_data.get('manager', old_manager)

        # Mettre à jour la boutique
        shop = super().update(instance, validated_data)

        # Si le manager a changé
        if old_manager != new_manager:
            # Retirer l'ancien manager
            if old_manager:
                old_manager.shop = None
                old_manager.save()

            # Assigner le nouveau manager
            if new_manager:
                new_manager.shop = shop
                new_manager.save()

        return shop


class ShopListSerializer(serializers.ModelSerializer):
    """
    Serializer minimal pour les listes de boutiques
    """
    manager_name = serializers.CharField(
        source='manager.get_full_name',
        read_only=True,
        allow_null=True
    )
    total_employees = serializers.IntegerField(read_only=True)

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'logo', 'phone_number',
            'city', 'manager', 'manager_name',
            'is_active', 'total_employees'
        ]


class ShopDetailSerializer(serializers.ModelSerializer):
    """
    Serializer détaillé avec informations sur les employés
    """
    manager_details = UserListSerializer(source='manager', read_only=True)
    employees = UserListSerializer(source='get_employees', many=True, read_only=True)
    total_employees = serializers.IntegerField(read_only=True)
    active_employees = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'slogan', 'logo', 'ifu',
            'phone_number', 'email', 'address', 'city', 'country',
            'manager', 'manager_details', 'employees',
            'is_active', 'total_employees', 'active_employees',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
