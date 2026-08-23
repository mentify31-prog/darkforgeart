"""
commissions/forms.py
"""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Commission, CommissionRevision, CommissionMessage


class CommissionRequestForm(forms.ModelForm):
    """Customer commission request form."""
    sketch_upload = forms.FileField(
        required=False,
        label=_("Upload your sketch (optional)"),
        help_text=_("Upload a scan or photo of your sketch"),
    )
    reference_0 = forms.FileField(required=False, label=_("Reference image 1"))
    reference_1 = forms.FileField(required=False, label=_("Reference image 2"))
    reference_2 = forms.FileField(required=False, label=_("Reference image 3"))

    class Meta:
        model = Commission
        fields = [
            "tier", "title", "description", "preferred_style",
            "preferred_colors", "dimensions", "intended_use",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }


class CommissionMessageForm(forms.ModelForm):
    class Meta:
        model = CommissionMessage
        fields = ["message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3, "placeholder": "Type your message..."})}


class AdminQuoteForm(forms.ModelForm):
    deposit_pct = forms.DecimalField(
        min_value=0,
        max_value=1,
        decimal_places=2,
        initial=0.5,
        label=_("Deposit fraction (e.g. 0.5 = 50%)"),
    )

    class Meta:
        model = Commission
        fields = ["quoted_price"]


class AdminRevisionUploadForm(forms.Form):
    preview_file = forms.FileField(label=_("Preview image (will be watermarked automatically)"))
    artist_notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label=_("Notes for the client"),
    )
