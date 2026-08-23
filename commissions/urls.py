"""
commissions/urls.py
"""
from django.urls import path
from . import views

app_name = "commissions"

urlpatterns = [
    # Customer
    path("request/", views.commission_request, name="commission_request"),
    path("my/", views.my_commissions, name="my_commissions"),
    path("<int:pk>/", views.commission_detail, name="commission_detail"),
    path("<int:pk>/message/", views.commission_message, name="commission_message"),
    path(
        "<int:pk>/revisions/<int:revision_pk>/respond/",
        views.commission_approve_revision,
        name="commission_approve_revision",
    ),

    # Admin
    path("admin/", views.admin_commissions_list, name="admin_commissions_list"),
    path("admin/<int:pk>/", views.admin_commission_detail, name="admin_commission_detail"),
    path("admin/<int:pk>/quote/", views.admin_quote_commission, name="admin_quote_commission"),
    path("admin/<int:pk>/preview/", views.admin_upload_preview, name="admin_upload_preview"),
    path("admin/<int:pk>/complete/", views.admin_complete_commission, name="admin_complete_commission"),
    path("admin/<int:pk>/message/", views.admin_message_commission, name="admin_message_commission"),
]
