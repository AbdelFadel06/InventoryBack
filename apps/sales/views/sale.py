# apps/sales/views/sale.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncDate
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from datetime import date

from apps.sales.models.sale import CashierSession, Sale, SaleItem, Expense
from apps.sales.serializers.sale import (
    CashierSessionSerializer, CashierSessionCreateSerializer,
    SaleSerializer, SaleListSerializer, SaleCreateSerializer,
    ExpenseSerializer,
)


class CashierSessionViewSet(viewsets.ModelViewSet):
    """Gestion des sessions de caisse — Manager/Admin uniquement"""
    queryset = CashierSession.objects.select_related(
        'shop', 'cashier', 'created_by'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['shop', 'status', 'cashier']
    ordering           = ['-start_date']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CashierSessionCreateSerializer
        return CashierSessionSerializer

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        if user.is_super_admin:
            return qs
        if user.shop:
            return qs.filter(shop=user.shop)
        return qs.none()

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Session active de la boutique courante"""
        today = timezone.now().date()
        shop  = request.user.shop

        if not shop and not request.user.is_super_admin:
            return Response({'error': 'Boutique non assignée.'}, status=400)

        qs = CashierSession.objects.filter(
            status='active',
            start_date__lte=today,
            end_date__gte=today,
        )
        if not request.user.is_super_admin:
            qs = qs.filter(shop=shop)

        session = qs.first()
        if not session:
            return Response({'session': None, 'message': 'Aucune session active.'})

        return Response(CashierSessionSerializer(session).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Clôturer une session"""
        session = self.get_object()
        if session.status == 'closed':
            return Response({'error': 'Session déjà clôturée.'}, status=400)
        session.status    = 'closed'
        session.closed_at = timezone.now()
        session.save()
        return Response(CashierSessionSerializer(session).data)


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.select_related(
        'shop', 'cashier', 'livreur', 'session'
    ).prefetch_related('items__product').all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['status', 'payment_method', 'payment_status', 'sale_type', 'livreur']
    ordering           = ['-created_at']
    http_method_names  = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return SaleCreateSerializer
        if self.action == 'list':
            return SaleListSerializer
        return SaleSerializer

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        if user.is_super_admin:
            shop_id = self.request.query_params.get('shop')
            if shop_id:
                qs = qs.filter(shop_id=shop_id)
        elif user.shop:
            qs = qs.filter(shop=user.shop)
            # Caissier voit toutes les ventes de sa session
            # Livreur voit ses livraisons
            if hasattr(user, 'role') and user.role == 'LIVREUR':
                qs = qs.filter(livreur=user)
        else:
            return qs.none()

        # Filtre par date
        date_str = self.request.query_params.get('date')
        if date_str:
            try:
                filter_date = date.fromisoformat(date_str)
                qs = qs.filter(created_at__date=filter_date)
            except ValueError:
                pass
        else:
            today = timezone.now().date()
            qs = qs.filter(created_at__date=today)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = SaleCreateSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        sale = serializer.save()
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Annuler une vente — remet le stock"""
        sale = self.get_object()
        if sale.status == 'cancelled':
            return Response({'error': 'Vente déjà annulée.'}, status=400)

        from apps.stocks.models import StockMovement
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            for item in sale.items.all():
                StockMovement.objects.create(
                    product=item.product,
                    shop=sale.shop,
                    movement_type='return',
                    quantity=item.quantity,
                    reference=sale.reference,
                    reason=f"Annulation vente {sale.reference}",
                    created_by=request.user,
                )
            sale.status = 'cancelled'
            sale.save(update_fields=['status'])

        return Response(SaleSerializer(sale).data)

    @action(detail=True, methods=['post'])
    def mark_delivered(self, request, pk=None):
        """Marquer une livraison comme livrée et payée"""
        sale = self.get_object()
        if sale.sale_type != 'delivery':
            return Response({'error': "Ce n'est pas une livraison."}, status=400)
        if sale.payment_status == 'paid':
            return Response({'error': 'Livraison déjà payée.'}, status=400)

        sale.payment_status = 'paid'
        sale.delivered_at   = timezone.now()
        sale.save(update_fields=['payment_status', 'delivered_at'])

        return Response(SaleSerializer(sale).data)

    @action(detail=False, methods=['get'])
    def daily_report(self, request):
        """
        Bilan journalier complet
        GET /api/sales/daily_report/?date=2026-03-23
        """
        user     = request.user
        date_str = request.query_params.get('date', str(timezone.now().date()))

        try:
            report_date = date.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'Format invalide. Utilisez YYYY-MM-DD.'}, status=400)

        qs = Sale.objects.filter(
            status='completed',
            created_at__date=report_date,
        )
        if not user.is_super_admin:
            if not user.shop:
                return Response({'error': 'Boutique non assignée.'}, status=400)
            qs = qs.filter(shop=user.shop)
        else:
            shop_id = request.query_params.get('shop')
            if shop_id:
                qs = qs.filter(shop_id=shop_id)

        # ── Totaux globaux ──────────────────────────────────────────
        totals = qs.aggregate(
            total_sales=Count('id'),
            total_amount=Sum('total_amount'),
            total_discount=Sum('total_discount'),
        )

        # ── Par moyen de paiement (ventes directes payées) ──────────
        cash_total  = qs.filter(payment_method='cash', payment_status='paid').aggregate(
            t=Sum('total_amount'))['t'] or 0
        momo_total  = qs.filter(payment_method='mobile_money', payment_status='paid').aggregate(
            t=Sum('total_amount'))['t'] or 0

        # ── Livraisons ──────────────────────────────────────────────
        deliveries_qs = qs.filter(sale_type='delivery')

        # Par livreur
        by_livreur = []
        livreurs = deliveries_qs.values(
            'livreur__id', 'livreur__first_name', 'livreur__last_name'
        ).annotate(
            total=Sum('total_amount'),
            paid=Sum('total_amount', filter=Q(payment_status='paid')),
            pending=Sum('total_amount', filter=Q(payment_status='pending')),
            count=Count('id'),
        )
        for l in livreurs:
            by_livreur.append({
                'livreur_id':   l['livreur__id'],
                'livreur_name': f"{l['livreur__first_name']} {l['livreur__last_name']}",
                'total':        l['total'] or 0,
                'paid':         l['paid']  or 0,
                'pending':      l['pending'] or 0,
                'count':        l['count'],
            })

        deliveries_paid    = deliveries_qs.filter(payment_status='paid').aggregate(t=Sum('total_amount'))['t'] or 0
        deliveries_pending = deliveries_qs.filter(payment_status='pending').aggregate(t=Sum('total_amount'))['t'] or 0

        # ── Récap articles vendus ───────────────────────────────────
        items_qs = SaleItem.objects.filter(
            sale__in=qs
        ).values(
            'product__id', 'product__name', 'product__sku', 'product__unit',
        ).annotate(
            total_qty=Sum('quantity'),
            total_subtotal=Sum('subtotal'),
            total_discount=Sum('discount_amount'),
            total_amount=Sum('total_price'),
        ).order_by('-total_amount')

        # ── Dépenses ────────────────────────────────────────────────
        shop_filter = {} if user.is_super_admin and not request.query_params.get('shop') else \
                      {'shop_id': request.query_params.get('shop')} if user.is_super_admin else \
                      {'shop': user.shop}
        expenses_qs = Expense.objects.filter(sale_date=report_date, **shop_filter)
        total_expenses = expenses_qs.aggregate(t=Sum('amount'))['t'] or 0
        expenses_list  = ExpenseSerializer(expenses_qs, many=True).data

        # ── Total net ───────────────────────────────────────────────
        total_collected = (cash_total or 0) + (momo_total or 0) + (deliveries_paid or 0)
        net_total       = total_collected - total_expenses

        return Response({
            'date':        str(report_date),
            'summary': {
                'total_sales':          totals['total_sales']   or 0,
                'total_amount':         totals['total_amount']  or 0,
                'total_discount':       totals['total_discount'] or 0,
                'cash_total':           cash_total,
                'momo_total':           momo_total,
                'deliveries_paid':      deliveries_paid,
                'deliveries_pending':   deliveries_pending,
                'total_expenses':       total_expenses,
                'total_collected':      total_collected,
                'net_total':            net_total,
            },
            'products_recap': list(items_qs),
            'by_livreur':     by_livreur,
            'expenses':       expenses_list,
        })

    @action(detail=False, methods=['get'])
    def monthly_summary(self, request):
        """
        Résumé journalier d'un mois — pour l'historique des ventes
        GET /api/sales/monthly_summary/?year=2026&month=3
        """
        try:
            year  = int(request.query_params.get('year',  timezone.now().year))
            month = int(request.query_params.get('month', timezone.now().month))
        except ValueError:
            return Response({'error': 'Paramètres invalides.'}, status=400)

        user = request.user
        qs = Sale.objects.filter(
            status='completed',
            created_at__year=year,
            created_at__month=month,
        )
        if not user.is_super_admin:
            if not user.shop:
                return Response({'error': 'Boutique non assignée.'}, status=400)
            qs = qs.filter(shop=user.shop)

        daily = (
            qs.annotate(day=TruncDate('created_at'))
              .values('day')
              .annotate(total_sales=Count('id'), total_amount=Sum('total_amount'))
              .order_by('day')
        )

        return Response({
            'year':  year,
            'month': month,
            'days':  [
                {
                    'date':         str(d['day']),
                    'total_sales':  d['total_sales'],
                    'total_amount': float(d['total_amount'] or 0),
                }
                for d in daily
            ],
        })

    @action(detail=False, methods=['get'])
    def livreur_point(self, request):
        """
        Point d'un livreur — ses livraisons du jour
        GET /api/sales/livreur_point/?livreur_id=X&date=2026-03-23
        """
        livreur_id = request.query_params.get('livreur_id')
        date_str   = request.query_params.get('date', str(timezone.now().date()))

        try:
            report_date = date.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'Format invalide.'}, status=400)

        qs = Sale.objects.filter(
            sale_type='delivery',
            status='completed',
            created_at__date=report_date,
        )
        if livreur_id:
            qs = qs.filter(livreur_id=livreur_id)
        elif request.user.role == 'LIVREUR':
            qs = qs.filter(livreur=request.user)

        if not request.user.is_super_admin:
            qs = qs.filter(shop=request.user.shop)

        paid    = qs.filter(payment_status='paid')
        pending = qs.filter(payment_status='pending')

        return Response({
            'date':            str(report_date),
            'total_count':     qs.count(),
            'paid_count':      paid.count(),
            'pending_count':   pending.count(),
            'total_paid':      paid.aggregate(t=Sum('total_amount'))['t'] or 0,
            'total_pending':   pending.aggregate(t=Sum('total_amount'))['t'] or 0,
            'deliveries':      SaleListSerializer(qs.prefetch_related('items__product'), many=True).data,
        })


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related('session', 'shop', 'created_by').all()
    permission_classes = [IsAuthenticated]
    serializer_class   = ExpenseSerializer
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['session', 'sale_date']

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        if user.is_super_admin:
            return qs
        if user.shop:
            return qs.filter(shop=user.shop)
        return qs.none()
