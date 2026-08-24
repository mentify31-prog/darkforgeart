"""
store/urls.py
"""
from django.urls import path
from . import views

app_name = "store"

urlpatterns = [
    path("", views.shop, name="shop"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/remove/<str:key>/", views.remove_from_cart, name="remove_from_cart"),
    path("cart/update/<str:key>/", views.update_cart, name="update_cart"),
    path("pinterest-catalog.csv", views.pinterest_catalog_feed, {"fmt": "csv"}, name="pinterest_catalog_csv"),
    path("pinterest-catalog.xml", views.pinterest_catalog_feed, {"fmt": "xml"}, name="pinterest_catalog_xml"),
]
