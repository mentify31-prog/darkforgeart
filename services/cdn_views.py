"""
services/cdn_views.py

High-performance authenticated proxy for GitHub-hosted preview images and assets.
Caches fetched assets locally to disk so subsequent requests serve in 1 millisecond.
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import quote, unquote

import requests
from django.conf import settings
from django.http import Http404, HttpResponse

CACHE_DIR = getattr(settings, "BASE_DIR", Path(".")) / "media" / "cdn_cache"


def _guess_content_type(filepath: str, upstream_type: str | None = None) -> str:
    if upstream_type and upstream_type != "application/octet-stream":
        return upstream_type
    guessed, _ = mimetypes.guess_type(filepath)
    return guessed or "image/jpeg"


def _fetch_github_asset(owner: str, repo: str, ref: str, filepath: str) -> tuple[bytes, str]:
    # 1. Check local disk cache first (0ms response time!)
    clean_path = unquote(filepath).lstrip("/")
    cache_key = f"{owner}_{repo}_{ref}_{clean_path.replace('/', '_')}"
    cache_file = CACHE_DIR / cache_key
    if cache_file.exists():
        try:
            data = cache_file.read_bytes()
            if len(data) > 0:
                return data, _guess_content_type(clean_path)
        except Exception:
            pass

    # 2. Fetch from GitHub via authenticated Contents API with raw media header
    token = getattr(settings, "GITHUB_TOKEN", "").strip()
    encoded_path = quote(clean_path, safe="/")
    content = None
    content_type = _guess_content_type(clean_path)

    if token:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3.raw",
        }
        try:
            api_resp = requests.get(api_url, headers=headers, params={"ref": ref}, timeout=20)
            if api_resp.status_code == 200 and len(api_resp.content) > 0:
                content = api_resp.content
                content_type = _guess_content_type(clean_path, api_resp.headers.get("Content-Type"))
        except requests.RequestException:
            pass

    # 3. Fallback: try raw.githubusercontent.com for public repos
    if content is None:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{encoded_path}"
        try:
            upstream = requests.get(raw_url, timeout=15)
            if upstream.status_code == 200 and len(upstream.content) > 0:
                content = upstream.content
                content_type = _guess_content_type(clean_path, upstream.headers.get("Content-Type"))
        except requests.RequestException:
            pass

    if content is None or len(content) == 0:
        raise Http404("Asset not found")

    # 4. Save to local disk cache for all future requests
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(content)
    except Exception:
        pass

    return content, content_type


def assets_proxy(request, filepath):
    """
    High-performance proxy with disk & HTTP browser caching.
    """
    repo = getattr(settings, "GITHUB_REPO", "").strip()
    branch = getattr(settings, "GITHUB_BRANCH", "main").strip() or "main"
    if not repo or "/" not in repo:
        raise Http404("Asset not found")

    owner, repo_name = repo.split("/", 1)
    content, content_type = _fetch_github_asset(owner, repo_name, branch, filepath)
    response = HttpResponse(content, content_type=content_type)
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def github_asset_proxy(request, owner, repo, ref, filepath):
    """Stream a file from any GitHub repo/ref/path combination with disk caching."""
    content, content_type = _fetch_github_asset(owner, repo, ref, filepath)
    response = HttpResponse(content, content_type=content_type)
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
