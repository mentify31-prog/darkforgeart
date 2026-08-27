"""
DarkForge Art - Base Settings
Shared across all environments. Sensitive values come from .env.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[2]  # DarkForgeArt/

# Load .env from project root (same level as manage.py)
load_dotenv(BASE_DIR / ".env", override=True)


# ─── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production-please")
raw_hosts = os.environ.get("ALLOWED_HOSTS", "*").split(",")
ALLOWED_HOSTS = [h.strip() for h in raw_hosts if h.strip()]

# Render external hostname auto-configuration
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Base URL for absolute links (emails, Paystack callbacks, downloads)
BASE_URL = os.environ.get(
    "BASE_URL",
    f"https://{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else "http://localhost:8000"
).rstrip("/")

# CSRF Trusted Origins
raw_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if raw_csrf:
    CSRF_TRUSTED_ORIGINS = [c.strip() for c in raw_csrf.split(",") if c.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        "https://*.onrender.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
if RENDER_EXTERNAL_HOSTNAME:
    origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)


# ─── Applications ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    # DarkForge Art apps
    "accounts",
    "gallery",
    "store",
    "orders",
    "commissions",
    "payments",
    "fulfillment",
]


# ─── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"


# ─── Templates ────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "context_processors.site_context",
                "store.context_processors.cart_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ─── Database - MySQL (mysqlclient, utf8mb4) ───────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "DarkForgeArt"),
        "USER": os.environ.get("DB_USER", "root"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            **({
                "ssl": {}
            } if os.environ.get("DB_SSL", "").lower() in ("true", "1", "yes") else {}),
        },
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}


# ─── Custom User Model ────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"


# ─── Auth ─────────────────────────────────────────────────────────────────────
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ─── Internationalization ─────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True


# ─── Static Files ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ─── Caching ──────────────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": os.environ.get(
            "CACHE_BACKEND",
            "django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": os.environ.get("CACHE_LOCATION", "darkforge-cache"),
        "TIMEOUT": int(os.environ.get("CACHE_TIMEOUT", "300")),
    }
}


# ─── Media (local dev only - prod uses GitHub raw URLs) ───────────────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ─── Default Primary Key ──────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─── Session ─────────────────────────────────────────────────────────────────
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 weeks
SESSION_COOKIE_HTTPONLY = True


# ─── Platform ─────────────────────────────────────────────────────────────────
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "DarkForge Art")
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


# ─── Paystack ─────────────────────────────────────────────────────────────────
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_WEBHOOK_SECRET = os.environ.get("PAYSTACK_WEBHOOK_SECRET", "")
PAYSTACK_CALLBACK_URL = os.environ.get("PAYSTACK_CALLBACK_URL", "")
PAYSTACK_CURRENCY = os.environ.get("PAYSTACK_CURRENCY", "KES")


# ─── GitHub Storage ───────────────────────────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")      # e.g. "username/darkforge-art-uploads"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_UPLOAD_DIR = os.environ.get("GITHUB_UPLOAD_DIR", "artwork")


# ─── Email (Resend.com) ───────────────────────────────────────────────────────
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
DEFAULT_FROM_EMAIL = (
    os.environ.get("FROM_EMAIL", "").strip()
    or os.environ.get("DEFAULT_FROM_EMAIL", "DarkForge Art <noreply@darkforgeart.store>").strip()
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
CONTACT_RECIPIENT_EMAIL = os.environ.get("CONTACT_RECIPIENT_EMAIL", "").strip()

if RESEND_API_KEY:
    EMAIL_BACKEND = "services.resend_backend.ResendEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ─── Google OAuth ─────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")


# ─── Admin Emails Whitelist ───────────────────────────────────────────────────
# Comma-separated emails automatically granted admin role on every login.
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
]


# ─── Fulfillment (Print-on-Demand) ────────────────────────────────────────────
PRINTFUL_API_KEY = os.environ.get("PRINTFUL_API_KEY", "")
PRINTFUL_STORE_ID = os.environ.get("PRINTFUL_STORE_ID", "")

PRINTIFY_API_KEY = os.environ.get("PRINTIFY_API_KEY", "")
PRINTIFY_SHOP_ID = os.environ.get("PRINTIFY_SHOP_ID", "")
PRINTIFY_INCLUDED_SHIPPING_USD = float(os.environ.get("PRINTIFY_INCLUDED_SHIPPING_USD", "9.99"))

# ─── Currency Conversion ──────────────────────────────────────────────────────
# KES to USD exchange rate for frontend display (1 USD = 130 KES default)
USD_EXCHANGE_RATE = float(os.environ.get("USD_EXCHANGE_RATE", "130.0"))

# ─── Pinterest Analytics & Conversion Tag ─────────────────────────────────────
PINTEREST_TAG_ID = os.environ.get("PINTEREST_TAG_ID", "")
