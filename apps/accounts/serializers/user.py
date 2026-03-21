from rest_framework import serializers
from apps.accounts.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer principal pour l'utilisateur
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone_number', 'gender', 'date_of_birth', 'profile_picture',
            'role', 'shop', 'shop_name', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'username']


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la création d'un utilisateur (Register)
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone_number',
            'gender', 'date_of_birth', 'role', 'shop'
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Les mots de passe ne correspondent pas."
            })

        # Seul SUPER_ADMIN peut créer d'autres SUPER_ADMIN
        request = self.context.get('request')
        if attrs.get('role') == 'SUPER_ADMIN':
            if not request or not request.user.is_super_admin:
                raise serializers.ValidationError({
                    "role": "Seul un Super Admin peut créer un autre Super Admin."
                })

        # SHOP_MANAGER et EMPLOYEE doivent avoir une boutique
        if attrs.get('role') in ['SHOP_MANAGER', 'EMPLOYEE']:
            if not attrs.get('shop'):
                raise serializers.ValidationError({
                    "shop": "Une boutique est requise pour ce rôle."
                })

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        user = User.objects.create_user(
            username=validated_data['email'].split('@')[0],
            password=password,
            **validated_data
        )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer pour la mise à jour d'un utilisateur
    """
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number',
            'gender', 'date_of_birth', 'profile_picture'
        ]

    def validate_profile_picture(self, value):
        """Valider la taille de l'image (max 5MB)"""
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "La taille de l'image ne doit pas dépasser 5MB."
            )
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer pour changer le mot de passe
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("L'ancien mot de passe est incorrect.")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "Les nouveaux mots de passe ne correspondent pas."
            })
        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class UserListSerializer(serializers.ModelSerializer):
    """
    Serializer minimal pour les listes d'utilisateurs
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'role',
            'shop', 'shop_name', 'is_active', 'profile_picture', 'created_at', 'phone_number'
        ]
