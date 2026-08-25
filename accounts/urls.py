"""
accounts/urls.py

URL patterns for DarkForge Art authentication and account management.
"""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Registration
    path("register/", views.register, name="register"),

    # Email verification
    path("verify-email/<uuid:token>/", views.verify_email, name="verify_email"),
    path("resend-verification/", views.resend_verification, name="resend_verification"),

    # Login / Logout
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("accept-terms/", views.accept_terms, name="accept_terms"),

    # Google OAuth
    path("google/", views.google_login, name="google_login"),
    path("google/callback/", views.google_callback, name="google_callback"),

    # Password Reset
    path(
        "password-reset/",
        views.DFAPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        views.DFAPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        views.DFAPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        views.DFAPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),

    # Customer dashboard & profile
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_view, name="profile"),

    # Admin
    path("admin-panel/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/customers/", views.admin_customers, name="admin_customers"),

    # Contact Support
    path("contact/", views.contact, name="contact"),

    # Legal & Merchant Policies
    path("refund-policy/", views.refund_policy, name="refund_policy"),
    path("terms-privacy/", views.terms_privacy_policy, name="terms_privacy"),
]
