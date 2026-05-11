from rest_framework import serializers
from apps.shops.models import Shop, ShopAssignment
from apps.accounts.serializers import UserListSerializer


class ShopSerializer(serializers.ModelSerializer):
    managers_details = UserListSerializer(source='managers', many=True, read_only=True)
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
            'managers', 'managers_details',
            'is_active', 'total_employees', 'active_employees',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']

    def validate_managers(self, value):
        for user in value:
            if user.role != 'SHOP_MANAGER':
                raise serializers.ValidationError(
                    f"{user.get_full_name()} n'est pas un manager de boutique."
                )
        return value

    def validate_logo(self, value):
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("La taille du logo ne doit pas dépasser 5MB.")
        return value


class ShopCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = [
            'name', 'slogan', 'logo', 'ifu',
            'phone_number', 'email', 'address', 'city', 'country',
            'managers'
        ]

    def validate_managers(self, value):
        for user in value:
            if user.role != 'SHOP_MANAGER':
                raise serializers.ValidationError(
                    f"{user.get_full_name()} n'est pas un manager de boutique."
                )
        return value

    def create(self, validated_data):
        managers = validated_data.pop('managers', [])
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user

        shop = Shop.objects.create(**validated_data)
        if managers:
            shop.managers.set(managers)
            # Mettre à jour shop sur chaque manager
            for m in managers:
                if not m.shop:
                    m.shop = shop
                    m.save(update_fields=['shop'])

        return shop


class ShopUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = [
            'name', 'slogan', 'logo', 'ifu',
            'phone_number', 'email', 'address', 'city', 'country',
            'managers', 'is_active'
        ]

    def validate_managers(self, value):
        for user in value:
            if user.role != 'SHOP_MANAGER':
                raise serializers.ValidationError(
                    f"{user.get_full_name()} n'est pas un manager de boutique."
                )
        return value

    def update(self, instance, validated_data):
        managers = validated_data.pop('managers', None)
        shop = super().update(instance, validated_data)
        if managers is not None:
            shop.managers.set(managers)
        return shop


class ShopListSerializer(serializers.ModelSerializer):
    managers_names = serializers.SerializerMethodField()
    total_employees = serializers.IntegerField(read_only=True)

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'logo', 'phone_number',
            'city', 'managers', 'managers_names',
            'is_active', 'total_employees'
        ]

    def get_managers_names(self, obj):
        return [m.get_full_name() for m in obj.managers.all()]


class ShopDetailSerializer(serializers.ModelSerializer):
    managers_details = UserListSerializer(source='managers', many=True, read_only=True)
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
            'managers', 'managers_details', 'employees',
            'is_active', 'total_employees', 'active_employees',
            'created_at', 'updated_at', 'created_by', 'created_by_name'
        ]


class ShopAssignmentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = ShopAssignment
        fields = [
            'id', 'user', 'user_name', 'shop', 'shop_name',
            'start_date', 'end_date', 'is_active',
            'assigned_by', 'assigned_by_name', 'note', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'assigned_by']


class ShopAssignEmployeesSerializer(serializers.Serializer):
    """Affecter plusieurs employés à une boutique en une seule requête."""
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1
    )
    start_date = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
