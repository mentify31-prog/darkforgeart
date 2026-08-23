"""
accounts/decorators.py

Access-control decorators for DarkForge Art.
"""
from functools import wraps

from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def admin_required(view_func):
    """Restrict view to admin users only."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        if not request.user.is_admin:
            return HttpResponseForbidden("You do not have permission to access this page.")
        return view_func(request, *args, **kwargs)
    return wrapper
