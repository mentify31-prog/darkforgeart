"""
commissions/views.py

Customer and admin commission views.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import admin_required
from .models import Commission, CommissionRevision, CommissionMessage
from .forms import (
    CommissionRequestForm,
    CommissionMessageForm,
    AdminQuoteForm,
    AdminRevisionUploadForm,
)
from services.email_service import (
    send_commission_received_email,
    send_commission_quoted_email,
    send_commission_preview_email,
    send_commission_completed_email,
)
from services.github_storage import get_github_service

logger = logging.getLogger("darkforge")


# ─── Customer Views ───────────────────────────────────────────────────────────

@login_required
def commission_request(request):
    """Customer submits a new commission request."""
    if request.method == "POST":
        form = CommissionRequestForm(request.POST, request.FILES)
        if form.is_valid():
            commission = form.save(commit=False)
            commission.client = request.user
            commission.status = Commission.Status.SUBMITTED

            # Handle sketch upload to GitHub
            sketch_file = request.FILES.get("sketch_upload")
            if sketch_file:
                try:
                    github = get_github_service()
                    result = github.upload_file(
                        sketch_file,
                        subdir="commissions/sketches",
                        filename_prefix=f"commission_{request.user.pk}",
                    )
                    if result:
                        commission.sketch_upload_url = result.stored_path
                except Exception as exc:
                    logger.warning("Failed to upload commission sketch: %s", exc)

            # Handle reference images (up to 5)
            ref_urls = []
            for i in range(5):
                ref_file = request.FILES.get(f"reference_{i}")
                if ref_file:
                    try:
                        github = get_github_service()
                        result = github.upload_file(
                            ref_file,
                            subdir="commissions/references",
                            filename_prefix=f"ref_{i}_{request.user.pk}",
                        )
                        if result:
                            ref_urls.append(result.stored_path)
                    except Exception as exc:
                        logger.warning("Failed to upload reference image %d: %s", i, exc)
            commission.reference_images = ref_urls

            commission.save()
            send_commission_received_email(commission)
            messages.success(
                request,
                "Your commission request has been submitted! "
                "We'll review it and get back to you with a quote.",
            )
            return redirect("commissions:my_commissions")
        messages.error(request, "Please correct the errors below.")
    else:
        form = CommissionRequestForm()

    return render(request, "commissions/request.html", {
        "form": form,
        "page_title": "Request a Custom Commission — DarkForge Art",
    })


@login_required
def my_commissions(request):
    """Customer's list of all their commissions."""
    commissions = Commission.objects.filter(
        client=request.user
    ).order_by("-created_at")
    return render(request, "commissions/my_commissions.html", {
        "commissions": commissions,
        "page_title": "My Commissions — DarkForge Art",
    })


@login_required
def commission_detail(request, pk):
    """Customer views their commission detail + message thread."""
    commission = get_object_or_404(Commission, pk=pk, client=request.user)
    revisions = commission.revisions.all()
    messages_qs = commission.messages.select_related("sender").all()

    context = {
        "commission": commission,
        "revisions": revisions,
        "messages": messages_qs,
        "message_form": CommissionMessageForm(),
        "page_title": f"Commission: {commission.title}",
    }
    return render(request, "commissions/commission_detail.html", context)


@login_required
def commission_message(request, pk):
    """Customer sends a message on their commission thread."""
    commission = get_object_or_404(Commission, pk=pk, client=request.user)
    if request.method == "POST":
        form = CommissionMessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.commission = commission
            msg.sender = request.user
            msg.save()
            messages.success(request, "Message sent.")
        else:
            messages.error(request, "Message could not be sent.")
    return redirect("commissions:commission_detail", pk=pk)


@login_required
def commission_approve_revision(request, pk, revision_pk):
    """Customer approves or requests revision on a preview."""
    commission = get_object_or_404(Commission, pk=pk, client=request.user)
    revision = get_object_or_404(CommissionRevision, pk=revision_pk, commission=commission)

    if request.method == "POST":
        response = request.POST.get("response")
        client_notes = request.POST.get("client_notes", "")
        if response == "approved":
            revision.client_response = CommissionRevision.ClientResponse.APPROVED
            revision.responded_at = timezone.now()
            revision.save(update_fields=["client_response", "responded_at"])
            commission.status = Commission.Status.FINAL_PAYMENT_DUE
            commission.save(update_fields=["status"])
            messages.success(request, "Preview approved! Final payment will now be processed.")
        elif response == "revision":
            revision.client_response = CommissionRevision.ClientResponse.REVISION_REQUESTED
            revision.client_notes = client_notes
            revision.responded_at = timezone.now()
            revision.save(update_fields=["client_response", "client_notes", "responded_at"])
            commission.status = Commission.Status.REVISION_REQUESTED
            commission.save(update_fields=["status"])
            messages.info(request, "Revision requested. The artist will be notified.")
    return redirect("commissions:commission_detail", pk=pk)


# ─── Admin Views ──────────────────────────────────────────────────────────────

@login_required
@admin_required
def admin_commissions_list(request):
    """Admin: all commissions with status filtering."""
    status_filter = request.GET.get("status")
    commissions = Commission.objects.select_related("client").order_by("-created_at")
    if status_filter:
        commissions = commissions.filter(status=status_filter)
    return render(request, "commissions/admin_list.html", {
        "commissions": commissions,
        "status_choices": Commission.Status.choices,
        "selected_status": status_filter,
        "page_title": "Commissions — Admin",
    })


@login_required
@admin_required
def admin_commission_detail(request, pk):
    """Admin: detailed commission view with full controls."""
    commission = get_object_or_404(Commission, pk=pk)
    revisions = commission.revisions.all()
    messages_qs = commission.messages.select_related("sender").all()

    context = {
        "commission": commission,
        "revisions": revisions,
        "messages": messages_qs,
        "message_form": CommissionMessageForm(),
        "quote_form": AdminQuoteForm(instance=commission),
        "revision_form": AdminRevisionUploadForm(),
        "page_title": f"Admin: {commission.title}",
    }
    return render(request, "commissions/admin_detail.html", context)


@login_required
@admin_required
def admin_quote_commission(request, pk):
    """Admin: set quote price on a commission."""
    commission = get_object_or_404(Commission, pk=pk)
    if request.method == "POST":
        form = AdminQuoteForm(request.POST, instance=commission)
        if form.is_valid():
            quoted = form.cleaned_data["quoted_price"]
            deposit_pct = float(form.cleaned_data.get("deposit_pct", 0.5))
            commission.set_quote(float(quoted), deposit_pct)
            send_commission_quoted_email(commission)
            messages.success(request, f"Quote of KES {quoted} sent to {commission.client.email}.")
        else:
            messages.error(request, "Quote form has errors.")
    return redirect("commissions:admin_commission_detail", pk=pk)


@login_required
@admin_required
def admin_upload_preview(request, pk):
    """Admin: upload a preview image for a commission revision."""
    commission = get_object_or_404(commission, pk=pk)
    if request.method == "POST":
        form = AdminRevisionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            preview_file = request.FILES.get("preview_file")
            artist_notes = form.cleaned_data.get("artist_notes", "")
            preview_url = ""
            if preview_file:
                try:
                    from services.watermark import create_preview_from_upload
                    preview_bytes = create_preview_from_upload(preview_file, slug=commission.title)
                    import io
                    preview_io = io.BytesIO(preview_bytes)
                    preview_io.name = f"preview_{commission.pk}.jpg"
                    github = get_github_service()
                    result = github.upload_file(
                        preview_io,
                        subdir="commissions/previews",
                        filename_prefix=f"commission_{commission.pk}",
                    )
                    if result:
                        preview_url = result.stored_path
                except Exception as exc:
                    logger.error("Failed to upload commission preview: %s", exc)
                    messages.error(request, "Failed to upload preview image.")
                    return redirect("commissions:admin_commission_detail", pk=pk)

            revision_number = commission.revisions.count() + 1
            revision = CommissionRevision.objects.create(
                commission=commission,
                revision_number=revision_number,
                artist_notes=artist_notes,
                preview_url=preview_url,
            )
            commission.status = Commission.Status.PREVIEW_SENT
            commission.save(update_fields=["status"])
            send_commission_preview_email(commission, revision)
            messages.success(request, f"Preview #{revision_number} uploaded and client notified.")
    return redirect("commissions:admin_commission_detail", pk=pk)


@login_required
@admin_required
def admin_complete_commission(request, pk):
    """Admin: mark commission as completed and release final file."""
    commission = get_object_or_404(Commission, pk=pk)
    if request.method == "POST":
        final_file = request.FILES.get("final_file")
        if final_file:
            try:
                github = get_github_service()
                result = github.upload_file(
                    final_file,
                    subdir="commissions/finals",
                    filename_prefix=f"commission_{commission.pk}",
                )
                if result:
                    commission.final_file_url = result.stored_path
            except Exception as exc:
                logger.error("Failed to upload final commission file: %s", exc)
                messages.error(request, "Failed to upload final file.")
                return redirect("commissions:admin_commission_detail", pk=pk)

        commission.status = Commission.Status.COMPLETED
        commission.save(update_fields=["status", "final_file_url"])
        send_commission_completed_email(commission)
        messages.success(request, "Commission marked complete and client notified.")
    return redirect("commissions:admin_commission_detail", pk=pk)


@login_required
@admin_required
def admin_message_commission(request, pk):
    """Admin: send a message on a commission thread."""
    commission = get_object_or_404(Commission, pk=pk)
    if request.method == "POST":
        form = CommissionMessageForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.commission = commission
            msg.sender = request.user
            msg.save()
    return redirect("commissions:admin_commission_detail", pk=pk)
