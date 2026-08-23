"""
gallery/urls.py
"""
from django.urls import path
from . import views

app_name = "gallery"

urlpatterns = [
    path("", views.home, name="home"),
    path("gallery/", views.gallery, name="gallery"),
    path("about/", views.about, name="about"),
    path("gallery/<slug:slug>/", views.artwork_detail, name="artwork_detail"),
]
