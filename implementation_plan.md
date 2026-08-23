# DarkForge Art — Django Platform Build Plan

## Project Overview

**DarkForge Art** is a premium art commerce platform for selling original hand-drawn dark/graffiti artwork transformed into digital products, physical merchandise, and custom commissions. The platform will be built with Django, MySQL, Paystack payments, Google Auth, Resend email, and a Printful/Printify fulfillment abstraction layer. Images are stored in a GitHub repository. The aesthetic is artistic and elegant — no boxy containers, no gradients — art speaks for itself.

---

## Architecture Diagram

```
                    DARKFORGE ART (Django)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
    DIGITAL ART         COMMISSIONS          PHYSICAL
        │                   │                   │
   GitHub Storage      Django DB          POD Abstraction
        │                   │               ┌───┴───┐
   Signed URLs         Commission          │       │
   on payment          Workflow        Printful  Printify
                                           │       │
                                        Print + Ship
                                               │
                                           Customer
                        └───────────────────┤
                                        PAYMENTS
                                            │
                                        Paystack
                                  (cards + M-Pesa via Paystack)
```

---

## Key Technical Decisions (from decisions.md)

| Decision | Choice |
|---|---|
| Framework | Django 5.x |
| Database | MySQL (with `dfa_` table prefix) |
| Payments | Paystack only (handles both cards and M-Pesa) |
| Auth | Google OAuth + email/password + password reset |
| Email | Resend |
| Image Storage | GitHub repo (via PyGithub) |
| POD Fulfillment | Printful + Printify (abstraction layer) |
| Reference project | EduAI (`C:\Users\adm\.vscode\Products\EduAI`) |

> [!IMPORTANT]
> The EduAI project patterns (custom User model, Paystack integration, GitHub image storage, Resend email backend, settings split, MySQL with prefix) are reused here. We adapt — not copy — those patterns to fit the art-commerce context.

---

## Build Phases

---

### PHASE 1 — Project Scaffolding & Core Setup

> Goal: A running Django project with correct settings, MySQL, environment config, and project structure.

#### Step 1.1 — Create Django Project & Directory Structure

**File/Folder layout:**
```
DarkForgeArt/
├── config/
│   ├── __init__.py
│   ├── urls.py
│   ├── wsgi.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       ├── development.py
│       └── production.py
├── accounts/
├── gallery/
├── store/
├── orders/
├── commissions/
├── payments/
├── fulfillment/
├── services/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
├── templates/
│   ├── base.html
│   ├── partials/
│   ├── accounts/
│   ├── gallery/
│   ├── store/
│   ├── orders/
│   └── commissions/
├── manage.py
├── requirements.txt
├── .env
├── .env.example
└── .gitignore
```

**Tasks:**
- `django-admin startproject config .`
- Create all app directories with `python manage.py startapp <app>`
- Create settings split: `base.py`, `development.py`, `production.py`
- Configure `manage.py` and `wsgi.py` to use `config.settings.development`

---

#### Step 1.2 — Requirements & Environment

**`requirements.txt`:**
```
Django==5.2.x
gunicorn
mysqlclient
python-dotenv
Pillow
PyGithub
requests
whitenoise
python-dateutil
```

**`.env` keys:**
```
DJANGO_SECRET_KEY=
DJANGO_SETTINGS_MODULE=config.settings.development
ALLOWED_HOSTS=127.0.0.1,localhost
DB_NAME=DarkForgeArt
DB_USER=root
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=3306
DB_TABLE_PREFIX=dfa_
PLATFORM_NAME=DarkForge Art
BASE_URL=http://127.0.0.1:8000
# Paystack
PAYSTACK_SECRET_KEY=
PAYSTACK_PUBLIC_KEY=
PAYSTACK_WEBHOOK_SECRET=
PAYSTACK_CALLBACK_URL=
# GitHub Storage
GITHUB_TOKEN=
GITHUB_REPO=username/darkforge-art-uploads
GITHUB_BRANCH=main
GITHUB_UPLOAD_DIR=artwork
# Resend
RESEND_API_KEY=
DEFAULT_FROM_EMAIL=noreply@darkforgeart.com
# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
ADMIN_EMAILS=
```

---

#### Step 1.3 — Base Settings (following EduAI pattern)

Configure `config/settings/base.py` with:
- MySQL database with `dfa_` prefix
- Whitenoise static files
- Custom user model: `accounts.User`
- Resend email backend
- GitHub upload settings
- Paystack keys
- Google OAuth keys
- Admin emails whitelist
- Africa/Nairobi timezone
- Media root (local dev only)

---

#### Step 1.4 — Database Helper & Table Prefix

Create `core/db.py` (or inline in each `models.py`) with:
```python
import os

def table_name(base_name: str) -> str:
    prefix = os.getenv("DB_TABLE_PREFIX", "dfa_")
    return f"{prefix}{base_name}"
```

All models will use `db_table = table_name("...")`.

---

### PHASE 2 — Authentication & User Accounts

> Goal: Full auth system: register, login, Google OAuth, password reset, email verification — matching EduAI's pattern but simplified for an art store.

#### Step 2.1 — Custom User Model (`accounts/models.py`)

**Fields:**
- `email` — unique, login field
- `username` — display name / handle
- `first_name`, `last_name`
- `role` — choices: `customer`, `admin`
- `phone` — optional, for order contact
- `avatar_url` — GitHub-hosted
- `is_email_verified`
- `created_at`, `updated_at`
- `db_table = table_name("users")`

**Profile model (separate):**
- `user` — OneToOne
- `bio` — artist bio for collectors
- `country`, `city`
- `newsletter_opt_in`

#### Step 2.2 — Auth Views & Forms

Following EduAI `accounts/views.py` pattern:

| URL | View | Description |
|---|---|---|
| `/accounts/register/` | `RegisterView` | Email + password signup |
| `/accounts/login/` | `LoginView` | Email/password login |
| `/accounts/logout/` | `LogoutView` | Logout |
| `/accounts/google/` | `GoogleOAuthView` | Initiate Google OAuth |
| `/accounts/google/callback/` | `GoogleCallbackView` | Handle Google callback |
| `/accounts/verify-email/<token>/` | `VerifyEmailView` | Email verification link |
| `/accounts/resend-verification/` | `ResendVerificationView` | Resend verification email |
| `/accounts/password-reset/` | `PasswordResetView` | Request reset link |
| `/accounts/password-reset/confirm/<uid>/<token>/` | `PasswordResetConfirmView` | Set new password |
| `/accounts/profile/` | `ProfileView` | View/edit profile |
| `/accounts/dashboard/` | `DashboardView` | Customer order/commission history |

#### Step 2.3 — Email Templates (Resend)

- `emails/verify_email.html`
- `emails/password_reset.html`
- `emails/welcome.html`

Reuse `services/resend_backend.py` from EduAI, adapted with DarkForge Art sender.

#### Step 2.4 — Google OAuth (manual flow, no allauth)

Following EduAI approach — manual Google OAuth2 flow using `requests`. No third-party library needed.

---

### PHASE 3 — Artwork & Gallery

> Goal: The core content system. Artwork is the heart of the business. This phase builds the gallery, product pages, and watermarked preview system.

#### Step 3.1 — Artwork Models (`gallery/models.py`)

```
Artwork
├── title
├── slug
├── description
├── style (neon graffiti / metal / cyberpunk / gothic / etc.)
├── artwork_type (original / digital / limited / merchandise_design)
├── original_pencil_url (GitHub)
├── colored_url (GitHub)
├── final_url (GitHub - full resolution, NEVER publicly exposed)
├── preview_url (GitHub - watermarked/low-res, public)
├── is_published
├── created_at
└── tags (M2M)

ArtworkImage (for process/step images on product page)
├── artwork (FK)
├── image_url (GitHub)
├── step_label (e.g. "Original Sketch", "Colored Version", "Final Art")
└── order

ArtworkTag
├── name
└── slug
```

#### Step 3.2 — GitHub Image Service (`services/github_storage.py`)

Reused from EduAI `PyGithub` pattern:
- `upload_image(file, path)` → returns GitHub raw URL
- `delete_image(path)`
- `get_signed_preview_url(path)` — for protected downloads (time-limited)

#### Step 3.3 — Watermark Service (`services/watermark.py`)

- `apply_watermark(image_path, text="DarkForge Art • Preview")` using Pillow
- Returns watermarked low-res preview
- Called when generating preview images for unpaid users

#### Step 3.4 — Gallery Views (`gallery/views.py`)

| URL | View | Description |
|---|---|---|
| `/` | `HomeView` | Featured artwork, hero section |
| `/gallery/` | `GalleryView` | Full artwork grid with filters |
| `/gallery/<slug>/` | `ArtworkDetailView` | Artwork page with process story |

**Important:** `final_url` is never sent to the template. Only `preview_url` (watermarked low-res) is shown before purchase.

---

### PHASE 4 — Product & Store System

> Goal: Four product types: Digital Art, Physical Products, Limited Editions, and Commercial Licenses.

#### Step 4.1 — Product Models (`store/models.py`)

```
ProductType (TextChoices)
├── DIGITAL        — downloadable file
├── PHYSICAL       — POD via Printful/Printify
├── LIMITED        — limited edition (digital or print, max copies)
└── LICENSE        — commercial/exclusive license

Product
├── artwork (FK to Artwork)
├── product_type
├── title
├── slug
├── description
├── price (DecimalField, KES stored, Paystack works in KES)
├── currency (default: KES)
├── is_active
├── created_at

DigitalProduct (extends Product via OneToOne or subclass)
├── product (OneToOne → Product)
├── file_url (GitHub — PRIVATE, signed URL on purchase)
├── file_size_bytes
├── license_type (personal / commercial / exclusive)

PhysicalProduct (extends Product)
├── product (OneToOne → Product)
├── printful_product_id
├── printify_product_id
├── fulfillment_provider (printful / printify)
├── sizes_available (JSON)
├── colors_available (JSON)
├── weight_grams

LimitedEdition (extends Product)
├── product (OneToOne → Product)
├── edition_size (e.g. 25)
├── edition_sold (counter)
├── edition_number_format (e.g. "001/025")
├── includes_original_sketch (Bool)
├── includes_print (Bool)
├── includes_digital (Bool)

LicenseProduct (extends Product)
├── product (OneToOne → Product)
├── license_scope (personal / commercial / exclusive)
├── usage_description
├── allowed_uses
```

#### Step 4.2 — Product Variant Model

For physical products with size/color options:
```
ProductVariant
├── physical_product (FK)
├── size (XS / S / M / L / XL / XXL)
├── color
├── printful_variant_id
├── printify_variant_id
├── price_override (optional)
├── stock_available (Bool)
```

#### Step 4.3 — Store Views (`store/views.py`)

| URL | View | Description |
|---|---|---|
| `/shop/` | `ShopView` | All products, filterable |
| `/shop/<slug>/` | `ProductDetailView` | Product page with variants |
| `/cart/` | `CartView` | Session-based cart |
| `/cart/add/<id>/` | `AddToCartView` | Add item to cart |
| `/cart/remove/<id>/` | `RemoveFromCartView` | Remove from cart |

#### Step 4.4 — Cart (Session-based)

Cart data stored in `request.session` — no DB model needed for cart itself. Cart items reference `Product.id` and `ProductVariant.id`.

---

### PHASE 5 — Orders

> Goal: Order system that handles both digital and physical product orders uniformly.

#### Step 5.1 — Order Models (`orders/models.py`)

```
Order
├── user (FK — null allowed for guest, but we encourage registration)
├── order_number (unique, e.g. DFA-2026-001234)
├── status (pending / paid / processing / fulfilled / cancelled / refunded)
├── total_amount
├── currency
├── shipping_name
├── shipping_email
├── shipping_address (JSON for physical products)
├── notes
├── created_at
├── updated_at

OrderItem
├── order (FK)
├── product (FK)
├── variant (FK → ProductVariant, nullable)
├── quantity
├── unit_price
├── subtotal
├── fulfillment_type (digital / physical / limited / license)
├── fulfillment_status (pending / sent / downloaded / shipped / delivered)

DigitalDelivery
├── order_item (OneToOne)
├── download_token (UUID, unique)
├── download_url_generated_at
├── download_count
├── max_downloads (default: 3)
├── expires_at
└── downloaded_at
```

#### Step 5.2 — Signed Download URL

```
/download/<uuid:token>/
```

View checks:
- Token exists and belongs to a paid order
- Not expired
- Under max download count
- Serves file via redirect to GitHub signed URL or streams it

---

### PHASE 6 — Payments (Paystack)

> Goal: Paystack integration for both card payments and M-Pesa (Paystack handles both in Kenya). Webhook-driven order fulfillment.

#### Step 6.1 — Payment Models (`payments/models.py`)

```
Payment
├── order (OneToOne)
├── paystack_reference (unique)
├── amount
├── currency (KES)
├── status (pending / success / failed / refunded)
├── provider (paystack)
├── payment_method (card / m-pesa / bank_transfer)
├── paystack_response (JSONField — raw webhook payload)
├── paid_at
├── created_at
```

#### Step 6.2 — Paystack Flow

Following EduAI `payments/views.py` pattern:

```
1. /checkout/                     → CheckoutView (summary + form)
2. /checkout/initiate/            → InitiatePaymentView
   → calls Paystack Initialize API
   → redirect customer to Paystack hosted page
3. /checkout/verify/<ref>/        → VerifyPaymentView (callback URL)
   → calls Paystack Verify API
   → marks order PAID
   → triggers fulfillment
4. /payments/webhook/             → PaystackWebhookView
   → validates HMAC signature
   → processes charge.success event
   → idempotent: checks if already processed
```

#### Step 6.3 — Post-Payment Actions

After payment confirmed:
- **Digital products**: generate `DigitalDelivery` record, send download email
- **Physical products**: create order in Printful/Printify via `fulfillment` app
- **Limited editions**: increment `edition_sold`, lock if sold out
- **Commission deposits**: update commission status to `deposit_paid`

---

### PHASE 7 — Commission System

> Goal: Full commission request workflow with multi-step status, deposit payment, preview/revision, and final delivery.

#### Step 7.1 — Commission Models (`commissions/models.py`)

```
CommissionTier (choices)
├── BASIC     — digital artwork, fixed price
├── PREMIUM   — custom + revisions
└── COMMERCIAL — commercial usage

Commission
├── client (FK → User)
├── tier
├── status (submitted / reviewing / quoted / deposit_paid /
│           in_progress / preview_sent / revision_requested /
│           final_payment_due / completed / cancelled)
├── title / description
├── preferred_style
├── preferred_colors
├── dimensions
├── intended_use (personal / commercial)
├── reference_images_json (list of GitHub URLs)
├── sketch_upload_url (GitHub)
├── quoted_price
├── deposit_amount
├── final_amount
├── admin_notes
├── created_at
├── updated_at

CommissionRevision
├── commission (FK)
├── revision_number
├── artist_notes
├── preview_url (GitHub — watermarked)
├── client_response (approved / revision_requested)
├── client_notes
├── created_at

CommissionMessage (simple Q&A thread)
├── commission (FK)
├── sender (FK → User)
├── message
├── attachment_url (optional)
├── created_at
```

#### Step 7.2 — Commission Views (`commissions/views.py`)

| URL | View | Who |
|---|---|---|
| `/commissions/request/` | `CommissionRequestView` | Customer |
| `/commissions/my/` | `MyCommissionsView` | Customer |
| `/commissions/<id>/` | `CommissionDetailView` | Customer |
| `/commissions/<id>/message/` | `CommissionMessageView` | Customer |
| `/admin/commissions/` | `AdminCommissionsListView` | Admin |
| `/admin/commissions/<id>/` | `AdminCommissionDetailView` | Admin |
| `/admin/commissions/<id>/quote/` | `AdminQuoteView` | Admin |
| `/admin/commissions/<id>/upload-preview/` | `AdminUploadPreviewView` | Admin |

#### Step 7.3 — Commission Email Notifications

Trigger emails (via Resend) on:
- New commission submitted → admin notified
- Quote sent → customer notified
- Deposit received → customer notified
- Preview uploaded → customer notified
- Final delivery → customer notified
- Commission completed → both parties

---

### PHASE 8 — Fulfillment Layer (POD)

> Goal: Abstract Printful and Printify behind a single interface so either can be swapped or used simultaneously.

#### Step 8.1 — Fulfillment Interface (`fulfillment/base.py`)

```python
class FulfillmentProvider:
    def create_order(self, order_item, shipping_address) -> dict: ...
    def get_order_status(self, external_order_id) -> dict: ...
    def cancel_order(self, external_order_id) -> bool: ...
    def get_shipping_rates(self, items, address) -> list: ...
```

#### Step 8.2 — Printful Provider (`fulfillment/printful.py`)

Implements `FulfillmentProvider`:
- `POST /orders` — create fulfillment order
- `GET /orders/{id}` — check status
- `DELETE /orders/{id}` — cancel (before fulfillment)

#### Step 8.3 — Printify Provider (`fulfillment/printify.py`)

Implements `FulfillmentProvider`:
- `POST /v1/shops/{shop_id}/orders.json`
- `GET /v1/shops/{shop_id}/orders/{id}.json`

#### Step 8.4 — Fulfillment Models (`fulfillment/models.py`)

```
FulfillmentOrder
├── order_item (OneToOne)
├── provider (printful / printify)
├── external_order_id
├── status (pending / submitted / processing / shipped / delivered / failed)
├── tracking_number
├── tracking_url
├── shipped_at
├── estimated_delivery
├── raw_response (JSONField)
├── created_at
├── updated_at
```

#### Step 8.5 — Fulfillment Webhooks

- `/fulfillment/printful/webhook/` — handles `package_shipped`, `order_fulfilled`
- `/fulfillment/printify/webhook/` — handles equivalent events
- Both update `FulfillmentOrder` and email customer with tracking info

---

### PHASE 9 — Admin Dashboard

> Goal: Artist-facing admin to manage everything without needing Django's built-in admin for day-to-day tasks.

#### Step 9.1 — Custom Admin Views (`accounts/views.py` — admin section)

| URL | View | Description |
|---|---|---|
| `/admin-panel/` | `AdminDashboardView` | Overview stats |
| `/admin-panel/artwork/` | `AdminArtworkListView` | Manage artwork |
| `/admin-panel/artwork/add/` | `AdminArtworkCreateView` | Upload new artwork |
| `/admin-panel/artwork/<id>/edit/` | `AdminArtworkEditView` | Edit artwork |
| `/admin-panel/products/` | `AdminProductListView` | All products |
| `/admin-panel/products/add/` | `AdminProductCreateView` | New product |
| `/admin-panel/orders/` | `AdminOrderListView` | All orders |
| `/admin-panel/orders/<id>/` | `AdminOrderDetailView` | Order detail |
| `/admin-panel/commissions/` | `AdminCommissionListView` | All commissions |
| `/admin-panel/commissions/<id>/` | `AdminCommissionDetailView` | Commission detail |
| `/admin-panel/customers/` | `AdminCustomerListView` | Customer list |

#### Step 9.2 — Admin Dashboard Stats

- Total revenue (today / this week / this month)
- Orders by status
- Active commissions
- Top-selling products
- Recent signups

---

### PHASE 10 — SEO & Frontend Styling

> Goal: Google-optimized, artistically styled frontend that communicates DarkForge Art's identity.

#### Step 10.1 — SEO Structure

For every page:
- Unique `<title>` tag
- Meta `description`
- Open Graph tags (`og:title`, `og:image`, `og:description`)
- Twitter card tags
- Canonical URLs
- `robots.txt`
- `sitemap.xml` (Django `django.contrib.sitemaps`)

**Structured Data (JSON-LD):**
- Product pages → `Product` schema
- Gallery pages → `ImageObject` / `CreativeWork` schema
- Homepage → `Organization` schema

#### Step 10.2 — Design Direction

Per `decisions.md`: *"artistic, no containers, no color gradients — something that preaches art and elegance."*

**Design language:**
- **Color palette**: Deep blacks, warm charcoals, off-whites, accent with deep crimson or electric ink-blue
- **Typography**: Display font (e.g. Cinzel or Playfair Display) for headings; clean sans-serif for body
- **Layout**: Full-bleed images, no card borders, masonry/grid gallery
- **Artwork presentation**: Full-width hero images, dark backgrounds, no white boxy containers
- **Animations**: Subtle fade-ins on scroll, ink-reveal effects — tasteful, not distracting

**Static files:**
```
static/
├── css/
│   ├── base.css      (reset, typography, variables)
│   ├── layout.css    (grid, spacing)
│   ├── gallery.css   (masonry, artwork cards)
│   ├── store.css     (product pages)
│   └── forms.css     (commission, checkout forms)
├── js/
│   ├── cart.js       (add-to-cart UX)
│   ├── gallery.js    (filter, lightbox)
│   └── checkout.js   (Paystack init)
```

**No Bootstrap or Tailwind** — custom CSS to keep the design unique and artistically controlled.

#### Step 10.3 — Template Structure

```
templates/
├── base.html                  (full-bleed layout, nav, footer)
├── partials/
│   ├── _nav.html
│   ├── _footer.html
│   ├── _messages.html
│   └── _artwork_card.html
├── gallery/
│   ├── home.html
│   ├── gallery.html
│   └── artwork_detail.html
├── store/
│   ├── shop.html
│   ├── product_detail.html
│   ├── cart.html
│   └── checkout.html
├── orders/
│   ├── order_confirmation.html
│   └── order_detail.html
├── commissions/
│   ├── request.html
│   ├── my_commissions.html
│   └── commission_detail.html
├── accounts/
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   └── profile.html
└── admin_panel/
    ├── dashboard.html
    ├── artwork_list.html
    └── ...
```

---

### PHASE 11 — Final Touches & Hardening

#### Step 11.1 — Security

- Signed, expiring download URLs for digital files
- HMAC validation on Paystack and POD webhooks
- `SECURE_*` settings in `production.py`
- No `/media/` publicly exposing artwork files
- Rate limiting on commission submit and checkout endpoints
- CSRF on all POST forms

#### Step 11.2 — Email Flows

| Trigger | Email |
|---|---|
| Registration | Welcome + verify email |
| Order paid (digital) | Order confirmation + download link |
| Order paid (physical) | Order confirmation + tracking info to follow |
| Commission submitted | Acknowledgement to customer + alert to admin |
| Commission quoted | Quote email to customer |
| Commission deposit paid | Confirmation + "work begins" message |
| Commission preview ready | Preview notification with revision instructions |
| Commission completed | Final delivery email |
| Fulfillment shipped | Shipping confirmation with tracking |

#### Step 11.3 — robots.txt & sitemap.xml

- Block `/admin/`, `/admin-panel/`, `/download/`, `/payments/webhook/`
- Sitemap includes: gallery, shop products, home, commission page

#### Step 11.4 — Performance

- WhiteNoise for static files
- Artwork preview images served via GitHub CDN raw URLs
- Database indexes on: `slug`, `status`, `created_at`, `user FK`
- `CONN_MAX_AGE` on MySQL connection

---

## Build Order Summary (Chronological)

| Phase | What Gets Built |
|---|---|
| **1** | Django project scaffold, MySQL, settings split, .env, requirements |
| **2** | Custom User model, auth (email/password + Google OAuth + password reset), email verification |
| **3** | Artwork model, GitHub image service, watermark service, gallery views |
| **4** | Product models (Digital / Physical / Limited / License), cart |
| **5** | Order models, signed download URLs, digital delivery |
| **6** | Paystack integration, checkout flow, webhook handler |
| **7** | Commission request system, multi-step workflow, admin tools |
| **8** | Fulfillment abstraction (Printful + Printify), fulfillment webhooks |
| **9** | Custom admin dashboard (artwork, products, orders, commissions) |
| **10** | SEO, artistic frontend styling, responsive templates |
| **11** | Security hardening, all email flows, robots.txt, sitemap, performance |

---

## Verification Plan

### After Each Phase
- Run `python manage.py check` — no errors
- Run `python manage.py migrate` — clean migrations
- Manually test the feature in a browser

### Automated
- Run `python manage.py test` at end of each phase

### Manual Verification Checkpoints
1. **Auth**: Register, verify email, login with Google, reset password
2. **Gallery**: Upload artwork via admin panel, view gallery, check watermark on preview
3. **Store**: Add product, add to cart, proceed to checkout
4. **Payments**: Complete a test Paystack payment (test mode), verify digital delivery email sent, verify download link works
5. **Commissions**: Submit a commission, admin quotes it, deposit paid, preview uploaded, final delivery
6. **Fulfillment**: Place a physical product order, verify Printful/Printify order created via API
7. **SEO**: Check page source for correct meta tags, run Google Rich Results Test on a product page
8. **Security**: Verify `/download/` URL fails after expiry, verify direct `/media/` access blocked

---

> [!NOTE]
> Each phase is built and verified before moving to the next. This mirrors the advice in `info.md`: *"Give it the architecture incrementally"* — you end up with a system you understand and can debug.
