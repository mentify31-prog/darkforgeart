"""
accounts/views.py

Auth + dashboard views for DarkForge Art.
Patterns adapted from EduAI (Mentify) accounts/views.py.
"""
import secrets
from urllib.parse import urlencode

import requests as http_requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.core.mail import send_mail
from django.db.models import Sum, Count
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from .forms import (
    RegistrationForm,
    EmailLoginForm,
    ProfileEditForm,
    DFAPasswordResetForm,
    DFASetPasswordForm,
)
from .models import User, Profile
from .decorators import admin_required
from services.email_service import send_welcome_email, send_verification_email

CURRENT_TERMS_VERSION = "2026-08-25"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _form_error_message(form, default="Please correct the errors below and try again."):
    if form.non_field_errors():
        return " ".join(str(error) for error in form.non_field_errors())
    for field, errors in form.errors.items():
        if errors:
            label = form.fields[field].label if field in form.fields else field.replace("_", " ").title()
            return f"{label}: {errors[0]}"
    return default


def promote_if_admin_email(user):
    """
    If the user's email is in settings.ADMIN_EMAILS, ensure they have
    admin role, is_superuser, and is_staff. Saves only if changed.
    """
    admin_emails = [e.strip().lower() for e in getattr(settings, "ADMIN_EMAILS", [])]
    if not admin_emails or user.email.lower() not in admin_emails:
        return
    changed = False
    if not user.is_superuser:
        user.is_superuser = True
        changed = True
    if not user.is_staff:
        user.is_staff = True
        changed = True
    if getattr(user, "role", None) != User.Role.ADMIN:
        user.role = User.Role.ADMIN
        changed = True
    if changed:
        user.save(update_fields=["is_superuser", "is_staff", "role"])


def _build_verify_url(request, user):
    return request.build_absolute_uri(
        reverse("accounts:verify_email", args=[str(user.email_verification_token)])
    )


# ─── Registration ─────────────────────────────────────────────────────────────

def register(request):
    """Customer registration with email + password."""
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            promote_if_admin_email(user)
            # Send verification email
            verify_url = _build_verify_url(request, user)
            send_verification_email(user, verify_url)
            # Log in immediately
            login(request, user)
            send_welcome_email(user)
            messages.success(
                request,
                f"Welcome to DarkForge Art, {user.first_name}! "
                "Please check your email to verify your account.",
            )
            return redirect(reverse("accounts:dashboard"))
        messages.error(request, _form_error_message(form))
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


# ─── Email Verification ───────────────────────────────────────────────────────

def verify_email(request, token):
    """Verify a user's email using the link sent during registration."""
    user = get_object_or_404(User, email_verification_token=token)
    if user.is_email_verified:
        messages.info(request, "Your email is already verified.")
    else:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        messages.success(request, "Your email has been verified. Thank you!")
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())
    return redirect("accounts:login")


@login_required
def resend_verification(request):
    """Resend the email verification link."""
    user = request.user
    if user.is_email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect(user.get_dashboard_url())
    user.regenerate_verification_token()
    verify_url = _build_verify_url(request, user)
    send_verification_email(user, verify_url)
    messages.success(request, "A new verification link has been sent to your email.")
    return redirect(user.get_dashboard_url())


# ─── Login / Logout ───────────────────────────────────────────────────────────

def login_view(request):
    """Custom login using email."""
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())

    if request.method == "POST":
        form = EmailLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            promote_if_admin_email(user)
            login(request, user)
            next_url = request.GET.get("next") or user.get_dashboard_url()
            messages.success(request, f"Welcome back, {user.first_name}!")
            return redirect(next_url)
        messages.error(request, _form_error_message(form, "Invalid email or password."))
    else:
        form = EmailLoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


@require_POST
@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You've been signed out. See you soon!")
    return redirect("gallery:home")


@require_POST
@login_required
def accept_terms(request):
    request.user.terms_accepted_at = timezone.now()
    request.user.terms_accepted_version = CURRENT_TERMS_VERSION
    request.user.save(update_fields=["terms_accepted_at", "terms_accepted_version"])
    messages.success(request, "Terms accepted. Thank you.")
    next_url = request.POST.get("next") or request.user.get_dashboard_url()
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = request.user.get_dashboard_url()
    return redirect(next_url)


# ─── Password Reset (Django built-in views, custom templates) ─────────────────

class DFAPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.txt"
    html_email_template_name = "accounts/emails/password_reset_email.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    form_class = DFAPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")

    def get_extra_email_context(self):
        return {"PLATFORM_NAME": getattr(settings, "PLATFORM_NAME", "DarkForge Art")}

    def form_valid(self, form):
        messages.info(
            self.request,
            "If an account exists for that email, a reset link has been sent.",
        )
        return super().form_valid(form)


class DFAPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class DFAPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = DFASetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        messages.success(self.request, "Your password has been updated. You can sign in now.")
        return super().form_valid(form)


class DFAPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


# ─── Google OAuth ─────────────────────────────────────────────────────────────

def google_login(request):
    """Initiates Google OAuth2 login flow."""
    if not settings.GOOGLE_CLIENT_ID:
        messages.error(request, "Google sign-in is not configured yet.")
        return redirect("accounts:login")

    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state

    redirect_uri = settings.GOOGLE_REDIRECT_URI or request.build_absolute_uri(
        reverse("accounts:google_callback")
    )

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return redirect(google_auth_url)


def google_callback(request):
    """Processes Google OAuth2 callback - creates or logs in user."""
    state = request.GET.get("state")
    session_state = request.session.pop("oauth_state", None)

    if not state or state != session_state:
        messages.error(request, "Google sign-in security check failed.")
        return redirect("accounts:login")

    code = request.GET.get("code")
    if not code:
        messages.info(request, "Google sign-in was cancelled.")
        return redirect("accounts:login")

    redirect_uri = settings.GOOGLE_REDIRECT_URI or request.build_absolute_uri(
        reverse("accounts:google_callback")
    )

    # Exchange authorization code for access token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        response = http_requests.post(token_url, data=token_data, timeout=15)
        if not response.ok:
            messages.error(request, "Google token exchange failed.")
            return redirect("accounts:login")
        access_token = response.json().get("access_token")
    except Exception:
        messages.error(request, "Failed to connect to Google authentication server.")
        return redirect("accounts:login")

    if not access_token:
        messages.error(request, "Google authentication did not return a valid token.")
        return redirect("accounts:login")

    # Fetch user profile
    profile_url = "https://www.googleapis.com/oauth2/v3/userinfo"
    try:
        profile_response = http_requests.get(
            profile_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if not profile_response.ok:
            messages.error(request, "Failed to fetch Google profile details.")
            return redirect("accounts:login")
        google_profile = profile_response.json()
    except Exception:
        messages.error(request, "Failed to connect to Google profile server.")
        return redirect("accounts:login")

    email = (google_profile.get("email") or "").strip().lower()
    if not email:
        messages.error(request, "Google authentication did not return an email address.")
        return redirect("accounts:login")

    user = User.objects.filter(email=email).first()

    if not user:
        # Auto-create account from Google profile
        name = google_profile.get("name") or email.split("@")[0]
        first_name = google_profile.get("given_name") or name.split()[0]
        last_name = google_profile.get("family_name") or (
            name.split()[1] if len(name.split()) > 1 else ""
        )
        base_username = email.split("@")[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.CUSTOMER,
        )
        user.is_email_verified = True  # Google verified their email
        avatar_url = google_profile.get("picture", "")
        if avatar_url:
            user.avatar_url = avatar_url[:1000]
        user.save(update_fields=["is_email_verified", "avatar_url"])
        Profile.objects.get_or_create(user=user)
        send_welcome_email(user)
        messages.success(request, f"Account created and signed in as {user.first_name}!")
    else:
        avatar_url = google_profile.get("picture", "")
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url[:1000]
            user.save(update_fields=["avatar_url"])
        messages.success(request, f"Welcome back, {user.first_name}!")

    promote_if_admin_email(user)
    login(request, user)
    next_url = request.GET.get("next") or user.get_dashboard_url()
    return redirect(next_url)


# ─── Customer Dashboard ───────────────────────────────────────────────────────

@login_required
def dashboard(request):
    """Customer dashboard: recent orders, active commissions."""
    from orders.models import Order
    from commissions.models import Commission

    recent_orders = (
        Order.objects.filter(user=request.user)
        .order_by("-created_at")[:5]
    )
    active_commissions = (
        Commission.objects.filter(client=request.user)
        .exclude(status__in=["completed", "cancelled"])
        .order_by("-created_at")[:5]
    )
    context = {
        "recent_orders": recent_orders,
        "active_commissions": active_commissions,
    }
    return render(request, "accounts/dashboard.html", context)


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

@login_required
@admin_required
def admin_dashboard(request):
    """Admin overview: revenue stats, recent orders, active commissions."""
    from orders.models import Order
    from commissions.models import Commission
    from django.utils import timezone
    from datetime import date

    today = date.today()

    # Revenue stats
    from payments.models import Payment
    monthly_revenue = (
        Payment.objects.filter(
            status=Payment.Status.SUCCESS,
            paid_at__year=today.year,
            paid_at__month=today.month,
        ).aggregate(total=Sum("amount"))["total"] or 0
    )

    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status="pending").count()
    recent_orders = Order.objects.select_related("user").order_by("-created_at")[:10]

    pending_commissions = Commission.objects.filter(
        status__in=["submitted", "reviewing", "quoted"]
    ).select_related("client").order_by("-created_at")[:10]

    total_customers = User.objects.filter(role=User.Role.CUSTOMER).count()

    context = {
        "monthly_revenue": monthly_revenue,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "recent_orders": recent_orders,
        "pending_commissions": pending_commissions,
        "total_customers": total_customers,
    }
    return render(request, "accounts/admin_dashboard.html", context)


# ─── Profile ──────────────────────────────────────────────────────────────────

@login_required
def profile_view(request):
    """View and edit user profile."""
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)

    if request.method == "POST":
        form = ProfileEditForm(request.POST, instance=profile, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")
        messages.error(request, _form_error_message(form))
    else:
        form = ProfileEditForm(instance=profile, user=user)

    return render(request, "accounts/profile.html", {"form": form, "profile": profile})


# ─── Admin: Customer List ─────────────────────────────────────────────────────

@login_required
@admin_required
def admin_customers(request):
    """Admin: list of all registered customers."""
    customers = (
        User.objects.filter(role=User.Role.CUSTOMER)
        .select_related("profile")
        .order_by("-created_at")
    )
    return render(request, "accounts/admin_customers.html", {"customers": customers})


# ─── Custom Error Handlers ────────────────────────────────────────────────────

def custom_404(request, exception=None):
    return render(request, "404.html", status=404)


def custom_500(request):
    return render(request, "500.html", status=500)


def custom_403(request, exception=None):
    return render(request, "403.html", status=403)


def custom_400(request, exception=None):
    return render(request, "400.html", status=400)


def contact(request):
    """
    Contact / Support view - allows customers and visitors to submit complaints,
    download help requests, or general inquiries.
    """
    from .forms import ContactForm
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"]
            email = form.cleaned_data["email"]
            category_label = dict(ContactForm.CATEGORY_CHOICES).get(form.cleaned_data["category"], "General")
            subject = form.cleaned_data["subject"]
            message_text = form.cleaned_data["message"]

            # Send email notification to Admin (checks CONTACT_RECIPIENT_EMAIL first, falls back to ADMIN_EMAILS)
            recipient_setting = getattr(settings, "CONTACT_RECIPIENT_EMAIL", "").strip()
            admin_emails = getattr(settings, "ADMIN_EMAILS", [])
            support_recipient = recipient_setting or (admin_emails[0] if admin_emails else "techbidmarketplace@gmail.com")

            try:
                from services.email_service import send_email_notification
                send_email_notification(
                    subject=f"[Support Request] {category_label}: {subject}",
                    recipient=support_recipient,
                    body=f"Name: {name}\nEmail: {email}\nCategory: {category_label}\nSubject: {subject}\n\nMessage:\n{message_text}",
                    reply_to=email,
                )
            except Exception as exc:
                logger.error("Failed to send support email: %s", exc)

            messages.success(
                request,
                "Thank you for contacting support! Your message has been received. Our team will get back to you via email within 24 hours."
            )
            return redirect("accounts:contact")
        else:
            messages.error(request, _form_error_message(form))
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                "name": request.user.get_full_name() or request.user.email.split("@")[0],
                "email": request.user.email,
            }
        form = ContactForm(initial=initial)

    context = {
        "form": form,
        "page_title": "Contact Support - DarkForge Art",
    }
    return render(request, "accounts/contact.html", context)


def refund_policy(request):
    """Render explicit Return & Refund Policy page for merchant guidelines compliance."""
    context = {
        "page_title": "Return & Refund Policy - DarkForge Art",
        "meta_description": "DarkForge Art Return, Refund and Replacement Policy for physical merchandise and digital products.",
    }
    return render(request, "legal/refund_policy.html", context)


def terms_privacy_policy(request):
    """Render Terms of Service & Privacy Policy page."""
    context = {
        "page_title": "Terms of Service & Privacy Policy - DarkForge Art",
        "meta_description": "Terms of Service, Shipping Guidelines, and Privacy Policy for DarkForge Art.",
    }
    return render(request, "legal/terms_privacy.html", context)
