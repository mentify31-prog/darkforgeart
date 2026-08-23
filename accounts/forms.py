"""
accounts/forms.py

Registration, login, profile, and password-reset forms.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _

from .models import User, Profile


class RegistrationForm(forms.ModelForm):
    """
    Email + password registration form.
    """
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "First name", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Last name", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "Email address", "autocomplete": "email"}),
    )
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Password", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Confirm password", "autocomplete": "new-password"}),
    )
    newsletter_opt_in = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Subscribe to new artwork releases and updates"),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("Passwords do not match."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        # Auto-generate username from email prefix (must be unique)
        base_username = email.split("@")[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        user.username = username
        user.email = email
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            # Create profile
            Profile.objects.create(
                user=user,
                newsletter_opt_in=self.cleaned_data.get("newsletter_opt_in", True),
            )
        return user


class EmailLoginForm(AuthenticationForm):
    """
    Login with email instead of username.
    """
    username = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={"placeholder": "Email address", "autofocus": True}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Password"}),
    )

    error_messages = {
        "invalid_login": _("Invalid email or password. Please try again."),
        "inactive": _("This account is inactive."),
    }


class ProfileEditForm(forms.ModelForm):
    """
    Edit the User first/last name, phone + Profile bio/location/newsletter fields.
    """
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = Profile
        fields = ["bio", "country", "city", "newsletter_opt_in"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4, "placeholder": "Tell us about yourself"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        if user:
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["phone"].initial = user.phone

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self._user:
            self._user.first_name = self.cleaned_data["first_name"]
            self._user.last_name = self.cleaned_data["last_name"]
            self._user.phone = self.cleaned_data.get("phone", "")
            if commit:
                self._user.save(update_fields=["first_name", "last_name", "phone"])
        if commit:
            profile.save()
        return profile


class DFAPasswordResetForm(PasswordResetForm):
    """Standard password reset form - email field only."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "Your email address"}),
    )


class DFASetPasswordForm(SetPasswordForm):
    """Set new password after reset link."""
    new_password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "New password"}),
    )
    new_password2 = forms.CharField(
        label=_("Confirm new password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}),
    )


class ContactForm(forms.Form):
    """
    Support / Contact Us form for customer complaints and inquiries.
    """
    CATEGORY_CHOICES = [
        ("general", "General Inquiry"),
        ("order", "Order & Payment Issue"),
        ("download", "Digital Download Help"),
        ("commission", "Custom Artwork Commission"),
        ("licensing", "Commercial Licensing"),
    ]

    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Your full name", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "Your email address", "autocomplete": "email"}),
    )
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Brief subject of your concern"}),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"placeholder": "Describe your complaint, question, or concern in detail...", "rows": 5}),
    )
    consent = forms.BooleanField(
        required=True,
        error_messages={"required": "You must consent to being contacted about your request."},
    )
