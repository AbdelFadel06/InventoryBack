"""
Totaux d'une liste paginée, sur toute la liste filtrée et pas seulement la page affichée.

GET /<liste>/counts/?search=…  → {"total": 42, "by": {"pending": 3, …}, …}

Pendant l'appel, la vue se présente comme la liste (`self.action = 'list'`) : mêmes
droits, même boutique, mêmes filtres. L'écran n'envoie pas le filtre de statut, pour
que chaque compteur couvre tous les statuts.
"""
from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.response import Response


class ListSummaryMixin:
    summary_group_by = None

    def initial(self, request, *args, **kwargs):
        if self.action == 'counts':
            self.action = 'list'
        super().initial(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def counts(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by().prefetch_related(None)
        return Response(self.build_summary(queryset))

    def build_summary(self, queryset):
        field = self.summary_group_by
        by = {str(row[field]): row['n'] for row in queryset.values(field).annotate(n=Count('pk'))}
        return {'total': sum(by.values()), 'by': by}
