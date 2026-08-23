"""
fulfillment/urls.py
"""
from django.urls import path
from . import views

app_name = "fulfillment"

urlpatterns = [
    path("printful/webhook/", views.printful_webhook, name="printful_webhook"),
    path("printify/webhook/", views.printify_webhook, name="printify_webhook"),
]
