from django.urls import path

from .views import CatalogView, HistoryView, RoleGridView, SwitchesView, UserPermissionsView

urlpatterns = [
    path('access/catalog/',             CatalogView.as_view(),         name='access-catalog'),
    path('access/roles/',               RoleGridView.as_view(),        name='access-roles'),
    path('access/users/<int:user_id>/', UserPermissionsView.as_view(), name='access-user'),
    path('access/switches/',            SwitchesView.as_view(),        name='access-switches'),
    path('access/history/',             HistoryView.as_view(),         name='access-history'),
]
