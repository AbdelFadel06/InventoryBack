from rest_framework import serializers

from apps.sales.models import SaleIssue


class SaleIssueSerializer(serializers.ModelSerializer):
    sale_reference   = serializers.CharField(source='sale.reference', read_only=True)
    sale_total       = serializers.DecimalField(source='sale.total_amount', max_digits=12, decimal_places=2, read_only=True)
    sale_status      = serializers.CharField(source='sale.status', read_only=True)
    sale_type        = serializers.CharField(source='sale.sale_type', read_only=True)
    shop             = serializers.IntegerField(source='sale.shop_id', read_only=True)
    shop_name        = serializers.CharField(source='sale.shop.name', read_only=True)
    reason_label     = serializers.CharField(source='get_reason_display', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.get_full_name', read_only=True, allow_null=True)
    resolved_by_name = serializers.CharField(source='resolved_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model  = SaleIssue
        fields = [
            'id', 'sale', 'sale_reference', 'sale_total', 'sale_status', 'sale_type', 'shop', 'shop_name',
            'reason', 'reason_label', 'comment', 'status',
            'reported_by_name', 'created_at',
            'resolved_by_name', 'resolved_at', 'resolution_note',
        ]
        read_only_fields = fields


class SaleIssueCreateSerializer(serializers.Serializer):
    reason  = serializers.ChoiceField(choices=SaleIssue.REASON_CHOICES)
    comment = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        attrs['comment'] = attrs['comment'].strip()
        if attrs['reason'] == 'other' and not attrs['comment']:
            raise serializers.ValidationError({'comment': "Précisez le problème."})
        return attrs
