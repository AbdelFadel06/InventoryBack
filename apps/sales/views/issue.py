from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.sales.models import SaleIssue
from apps.sales.permissions import IsManagerOrAdmin
from apps.sales.serializers.issue import SaleIssueSerializer
from apps.shops.mixins import ActiveShopMixin


class SaleIssueViewSet(ActiveShopMixin, viewsets.ReadOnlyModelViewSet):
    """Signalements à traiter par le manager, au point du soir."""
    queryset = SaleIssue.objects.select_related('sale__shop', 'reported_by', 'resolved_by').all()
    serializer_class = SaleIssueSerializer
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'sale']

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()
        user = self.request.user
        if user.is_super_admin:
            return queryset
        # ?scope=all : la cloche du manager couvre toutes ses boutiques, pas seulement l'active.
        if self.request.query_params.get('scope') == 'all':
            return queryset.filter(sale__shop__in=user.managed_shops.all())
        active_shop = self.get_active_shop(self.request)
        if active_shop:
            return queryset.filter(sale__shop=active_shop)
        return queryset.none()

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        issue = self.get_object()
        if issue.status == 'resolved':
            return Response({'error': 'Ce signalement est déjà traité.'}, status=400)

        note = (request.data.get('note') or '').strip()
        if not note:
            return Response({'error': 'Indiquez comment le problème a été traité.'}, status=400)

        issue.status = 'resolved'
        issue.resolved_by = request.user
        issue.resolved_at = timezone.now()
        issue.resolution_note = note
        issue.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_note'])
        return Response(SaleIssueSerializer(issue).data)
