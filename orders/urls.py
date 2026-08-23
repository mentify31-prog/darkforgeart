"""
orders/urls.py
"""
from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("confirmation/<str:order_number>/", views.order_confirmation, name="order_confirmation"),
    path("download/<uuid:token>/", views.download, name="download"),
    path("detail/<str:order_number>/", views.order_detail, name="order_detail"),
    path("verify-payment/<str:order_number>/", views.verify_order_payment, name="verify_order_payment"),
]
