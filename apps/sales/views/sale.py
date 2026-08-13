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
from apps.shops.mixins import ActiveShopMixin


class CashierSessionViewSet(ActiveShopMixin, viewsets.ModelViewSet):
    """Gestion des sessions de caisse — Manager/Admin uniquement"""
    queryset = CashierSession.objects.select_related(
        'shop', 'cashier', 'created_by'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['shop', 'status', 'cashier']
    search_fields      = ['cashier__first_name', 'cashier__last_name', 'cashier__email']
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
        active_shop = self.get_active_shop(self.request)
        if active_shop:
            return qs.filter(shop=active_shop)
        return qs.none()

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Session active — filtrée par caissier pour les employés, par shop pour managers/admins"""
        today = timezone.now().date()
        user  = request.user
        shop  = self.get_active_shop(request)

        if not shop and not user.is_super_admin:
            return Response({'error': 'Boutique non assignée.'}, status=400)

        qs = CashierSession.objects.filter(
            status='active',
            start_date__lte=today,
            end_date__gte=today,
        )

        if user.is_super_admin:
            pass  # voit toutes les sessions
        elif getattr(user, 'role', None) == 'EMPLOYEE':
            # Un caissier ne voit que SA session
            qs = qs.filter(shop=shop, cashier=user)
        else:
            # Manager : toutes les sessions du shop
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


class SaleViewSet(ActiveShopMixin, viewsets.ModelViewSet):
    queryset = Sale.objects.select_related(
        'shop', 'cashier', 'livreur', 'session'
    ).prefetch_related('items__product').all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['status', 'payment_method', 'payment_status', 'sale_type', 'livreur']
    search_fields      = ['reference', 'cashier__first_name', 'cashier__last_name', 'livreur__first_name', 'livreur__last_name']
    ordering           = ['-created_at']
    http_method_names  = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return SaleCreateSerializer
        if self.action == 'list':
            return SaleListSerializer
        return SaleSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['active_shop'] = self.get_active_shop(self.request)
        return ctx

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        if user.is_super_admin:
            shop_id = self.request.query_params.get('shop')
            if shop_id:
                qs = qs.filter(shop_id=shop_id)
        else:
            active_shop = self.get_active_shop(self.request)
            if not active_shop:
                return qs.none()
            qs = qs.filter(shop=active_shop)
            # Livreur voit uniquement ses propres livraisons
            if hasattr(user, 'role') and user.role == 'LIVREUR':
                qs = qs.filter(livreur=user)

        # Filtre par date — uniquement sur la liste, pas sur le détail/cancel/mark_delivered
        if self.action == 'list':
            # ?all=true → pas de filtre date (pour stats livreurs, historique complet)
            if self.request.query_params.get('all') == 'true':
                pass
            else:
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
            data=request.data,
            context={'request': request, 'active_shop': self.get_active_shop(request)},
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
    def modify_items(self, request, pk=None):
        """Modifier le contenu d'une livraison (quantités, ajout, suppression) avec ajustement du stock."""
        from apps.stocks.models import StockMovement
        from apps.products.models import Product
        from django.db import transaction as db_transaction
        from decimal import Decimal

        sale = self.get_object()

        if sale.sale_type != 'delivery':
            return Response({'error': "Seules les livraisons peuvent être modifiées."}, status=400)
        if sale.status == 'cancelled':
            return Response({'error': "Cette livraison est annulée."}, status=400)

        raw_items = request.data.get('items', [])
        if not raw_items:
            return Response({'error': "Au moins un article est requis."}, status=400)

        # Parse and validate input
        new_items = {}
        for raw in raw_items:
            try:
                pid = int(raw['product_id'])
                qty = int(raw['quantity'])
            except (KeyError, TypeError, ValueError):
                return Response({'error': "product_id (entier) et quantity (entier > 0) requis."}, status=400)
            if qty <= 0:
                return Response({'error': f"Quantité invalide pour produit {pid}."}, status=400)
            new_items[pid] = {
                'quantity': qty,
                'unit_price': raw.get('unit_price'),
            }

        # Pre-validate that new products exist
        current_ids = set(sale.items.values_list('product_id', flat=True))
        for pid in new_items:
            if pid not in current_ids:
                if not Product.objects.filter(id=pid, is_active=True).exists():
                    return Response({'error': f"Produit ID {pid} introuvable."}, status=400)

        with db_transaction.atomic():
            current_items = {item.product_id: item for item in sale.items.select_related('product').all()}

            # Removed items — restore full qty to stock
            for pid, item in list(current_items.items()):
                if pid not in new_items:
                    StockMovement.objects.create(
                        product=item.product,
                        shop=sale.shop,
                        movement_type='return',
                        quantity=item.quantity,
                        reference=sale.reference,
                        reason=f"Modif. livraison {sale.reference} — suppression article",
                        created_by=request.user,
                    )
                    item.delete()

            # Updated items — adjust stock difference
            for pid, item in current_items.items():
                if pid in new_items:
                    new_qty = new_items[pid]['quantity']
                    diff = new_qty - item.quantity
                    if diff < 0:
                        StockMovement.objects.create(
                            product=item.product,
                            shop=sale.shop,
                            movement_type='return',
                            quantity=-diff,
                            reference=sale.reference,
                            reason=f"Modif. livraison {sale.reference} — réduction qté",
                            created_by=request.user,
                        )
                    elif diff > 0:
                        StockMovement.objects.create(
                            product=item.product,
                            shop=sale.shop,
                            movement_type='exit',
                            quantity=-diff,
                            reference=sale.reference,
                            reason=f"Modif. livraison {sale.reference} — augmentation qté",
                            created_by=request.user,
                        )
                    item.quantity = new_qty
                    raw_price = new_items[pid]['unit_price']
                    if raw_price is not None:
                        item.unit_price = Decimal(str(raw_price))
                    item.save()

            # New items — decrement stock
            for pid, data in new_items.items():
                if pid not in current_items:
                    product = Product.objects.get(id=pid, is_active=True)
                    unit_price = Decimal(str(data['unit_price'])) if data['unit_price'] else product.selling_price
                    SaleItem(
                        sale=sale,
                        product=product,
                        quantity=data['quantity'],
                        unit_price=unit_price,
                    ).save()
                    StockMovement.objects.create(
                        product=product,
                        shop=sale.shop,
                        movement_type='exit',
                        quantity=-data['quantity'],
                        reference=sale.reference,
                        reason=f"Modif. livraison {sale.reference} — ajout article",
                        created_by=request.user,
                    )

            # Recalculate from fresh DB query — avoids stale prefetch_related cache
            fresh_items = SaleItem.objects.filter(sale=sale)
            sale.subtotal       = sum(item.subtotal       for item in fresh_items)
            sale.total_discount = sum(item.discount_amount for item in fresh_items)
            sale.total_amount   = sale.subtotal - sale.total_discount
            sale.save(update_fields=['subtotal', 'total_discount', 'total_amount'])

        # Return fresh serialized data (prefetch cache on sale is stale)
        fresh_sale = (
            Sale.objects
            .select_related('shop', 'cashier', 'livreur', 'session')
            .prefetch_related('items__product')
            .get(id=sale.id)
        )
        return Response(SaleSerializer(fresh_sale).data)

    @action(detail=True, methods=['post'])
    def mark_delivered(self, request, pk=None):
        """Livreur confirme avoir collecté le paiement client."""
        sale = self.get_object()
        if sale.sale_type != 'delivery':
            return Response({'error': "Ce n'est pas une livraison."}, status=400)
        if sale.status == 'cancelled':
            return Response({'error': 'Livraison annulée.'}, status=400)
        if sale.delivered_at:
            return Response({'error': 'Collecte déjà confirmée par le livreur.'}, status=400)

        sale.delivered_at = timezone.now()
        sale.save(update_fields=['delivered_at'])
        return Response(SaleSerializer(sale).data)

    @action(detail=True, methods=['post'])
    def validate_payment(self, request, pk=None):
        """Caissier/manager valide la réception du paiement du livreur."""
        sale = self.get_object()
        if sale.sale_type != 'delivery':
            return Response({'error': "Ce n'est pas une livraison."}, status=400)
        if sale.status == 'cancelled':
            return Response({'error': 'Livraison annulée.'}, status=400)
        if sale.payment_status == 'paid':
            return Response({'error': 'Paiement déjà validé.'}, status=400)

        sale.payment_status = 'paid'
        if not sale.delivered_at:
            sale.delivered_at = timezone.now()
        sale.save(update_fields=['payment_status', 'delivered_at'])
        return Response(SaleSerializer(sale).data)

    @action(detail=True, methods=['post'])
    def mark_livreur_paid(self, request, pk=None):
        """Marquer la commission livreur comme payée"""
        sale = self.get_object()
        if sale.sale_type != 'delivery':
            return Response({'error': "Ce n'est pas une livraison."}, status=400)
        if sale.livreur_paid:
            return Response({'error': 'Commission déjà marquée comme payée.'}, status=400)

        sale.livreur_paid = True
        sale.save(update_fields=['livreur_paid'])
        return Response({'message': 'Commission livreur marquée comme payée.', 'sale_id': sale.id})

    @action(detail=False, methods=['post'])
    def mark_livreur_paid_bulk(self, request):
        """Marquer plusieurs commissions livreur comme payées en une fois.
        Body: { "sale_ids": [1, 2, 3], "livreur_id": 5 }"""
        sale_ids   = request.data.get('sale_ids', [])
        livreur_id = request.data.get('livreur_id')
        if not sale_ids or not livreur_id:
            return Response({'error': 'sale_ids et livreur_id requis.'}, status=400)

        qs = Sale.objects.filter(
            id__in=sale_ids,
            livreur_id=livreur_id,
            sale_type='delivery',
            livreur_paid=False,
        )
        if not request.user.is_super_admin:
            active_shop = self.get_active_shop(request)
            if active_shop:
                qs = qs.filter(shop=active_shop)

        count = qs.update(livreur_paid=True)
        return Response({'message': f'{count} commission(s) marquée(s) comme payée(s).', 'count': count})

    @action(detail=False, methods=['get'])
    def livreur_stats(self, request):
        """
        Stats de tous les livreurs pour la boutique active.
        GET /api/sales/livreur_stats/
        """
        user = request.user
        qs = Sale.objects.filter(sale_type='delivery', status='completed')

        if user.is_super_admin:
            shop_id = request.query_params.get('shop')
            if shop_id:
                qs = qs.filter(shop_id=shop_id)
        else:
            active_shop = self.get_active_shop(request)
            if not active_shop:
                return Response([])
            qs = qs.filter(shop=active_shop)

        # Agréger par livreur
        stats = (
            qs.values('livreur__id', 'livreur__first_name', 'livreur__last_name')
            .annotate(
                total_colis=Count('id'),
                colis_payes=Count('id', filter=Q(livreur_paid=True)),
                colis_non_payes=Count('id', filter=Q(livreur_paid=False)),
                montant_total=Sum('total_amount'),
            )
            .order_by('livreur__last_name')
        )

        return Response([
            {
                'livreur_id':      s['livreur__id'],
                'livreur_name':    f"{s['livreur__first_name']} {s['livreur__last_name']}",
                'total_colis':     s['total_colis'],
                'colis_payes':     s['colis_payes'],
                'colis_non_payes': s['colis_non_payes'],
                'montant_total':   float(s['montant_total'] or 0),
            }
            for s in stats
        ])

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
        active_shop = None
        if not user.is_super_admin:
            active_shop = self.get_active_shop(request)
            if not active_shop:
                return Response({'error': 'Boutique non assignée.'}, status=400)
            qs = qs.filter(shop=active_shop)
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

        # ── Par moyen de paiement (toutes ventes payées confondues) ───
        # Espèces : cash direct + livraisons encaissées à la livraison
        cash_total = qs.filter(
            payment_method__in=['cash', 'on_delivery'], payment_status='paid'
        ).aggregate(t=Sum('total_amount'))['t'] or 0

        # Mobile Money : momo direct + livraisons prépayées par momo
        momo_total = qs.filter(
            payment_method='mobile_money', payment_status='paid'
        ).aggregate(t=Sum('total_amount'))['t'] or 0

        # ── Livraisons ──────────────────────────────────────────────
        deliveries_qs = qs.filter(sale_type='delivery')

        # Par livreur — uniquement les livraisons non payées
        by_livreur = []
        pending_qs = deliveries_qs.filter(payment_status='pending')
        livreurs = pending_qs.values(
            'livreur__id', 'livreur__first_name', 'livreur__last_name'
        ).annotate(
            pending_amount=Sum('total_amount'),
            pending_count=Count('id'),
        )
        for l in livreurs:
            by_livreur.append({
                'livreur_id':     l['livreur__id'],
                'livreur_name':   f"{l['livreur__first_name']} {l['livreur__last_name']}",
                'pending_amount': l['pending_amount'] or 0,
                'pending_count':  l['pending_count'],
            })

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
                      {'shop': active_shop}
        expenses_qs = Expense.objects.filter(sale_date=report_date, **shop_filter)
        total_expenses = expenses_qs.aggregate(t=Sum('amount'))['t'] or 0
        expenses_list  = ExpenseSerializer(expenses_qs, many=True).data

        # ── Total net ───────────────────────────────────────────────
        total_collected = cash_total + momo_total
        net_total       = total_collected - total_expenses

        return Response({
            'date':        str(report_date),
            'summary': {
                'total_sales':          totals['total_sales']   or 0,
                'total_amount':         totals['total_amount']  or 0,
                'total_discount':       totals['total_discount'] or 0,
                'cash_total':          cash_total,
                'momo_total':          momo_total,
                'deliveries_pending':  deliveries_pending,
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
            active_shop = self.get_active_shop(request)
            if not active_shop:
                return Response({'error': 'Boutique non assignée.'}, status=400)
            qs = qs.filter(shop=active_shop)

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

        # Managers/employees: filtered to their active shop
        # Livreurs: all their deliveries across all shops
        if not request.user.is_super_admin and request.user.role != 'LIVREUR':
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
            'deliveries':      SaleSerializer(qs.prefetch_related('items__product'), many=True).data,
        })


class ExpenseViewSet(ActiveShopMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.select_related('session', 'shop', 'created_by').all()
    permission_classes = [IsAuthenticated]
    serializer_class   = ExpenseSerializer
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['session', 'sale_date']

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['active_shop'] = self.get_active_shop(self.request)
        return ctx

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        if user.is_super_admin:
            return qs
        active_shop = self.get_active_shop(self.request)
        if active_shop:
            return qs.filter(shop=active_shop)
        return qs.none()
