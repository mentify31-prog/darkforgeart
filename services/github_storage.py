"""
services/github_storage.py

Adapted from EduAI services/github_service.py.
Handles upload, download, and deletion of artwork files in a GitHub repository.
DarkForge Art specific: supports artwork preview vs final file routing.
"""
from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import requests
from django.conf import settings


@dataclass(slots=True)
class GitHubUploadResult:
    repo_path: str      # e.g. "artwork/previews/abc123_skull_preview.jpg"
    stored_path: str    # e.g. "github://username/darkforge-art-uploads/main/artwork/..."
    public_url: str     # raw.githubusercontent.com URL for direct access


class GitHubStorageService:
    """
    Uploads, downloads, and deletes files in a GitHub repository via the Contents API.
    Used for storing artwork images (previews and protected full-res files).
    """

    def __init__(
        self,
        token: str,
        repo_name: str,
        branch: str = "main",
        upload_dir: str = "artwork",
    ) -> None:
        if not token or not repo_name:
            raise ValueError("GITHUB_TOKEN and GITHUB_REPO are required.")
        self.repo_name = repo_name
        self.branch = branch
        self.upload_dir = upload_dir.strip("/")
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        })

    def _get_file_sha(self, path: str) -> Optional[str]:
        """Get the SHA of an existing file (needed for updates/deletes)."""
        resp = self.session.get(
            f"{self.base_url}/repos/{self.repo_name}/contents/{path}",
            params={"ref": self.branch},
        )
        if resp.status_code >= 300:
            return None
        data = resp.json()
        if isinstance(data, dict):
            return data.get("sha")
        return None

    def _commit_file(self, path: str, content: bytes, message: str) -> None:
        """Create or update a file in the repo."""
        encoded = base64.b64encode(content).decode("utf-8")
        payload: dict = {
            "message": message,
            "content": encoded,
            "branch": self.branch,
        }
        sha = self._get_file_sha(path)
        if sha:
            payload["sha"] = sha

        resp = self.session.put(
            f"{self.base_url}/repos/{self.repo_name}/contents/{path}",
            json=payload,
            timeout=60,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"GitHub upload failed: {resp.status_code} {resp.text}")

    def upload_file(
        self,
        file_obj,
        subdir: str | None = None,
        filename_prefix: str = "",
    ) -> GitHubUploadResult | None:
        """
        Upload a file-like object (e.g. Django UploadedFile) to GitHub.
        Returns a GitHubUploadResult or None if file is empty.

        subdir: optional subdirectory under upload_dir (e.g. "previews", "originals")
        filename_prefix: optional prefix added to the filename (e.g. artwork slug)
        """
        if not file_obj:
            return None

        filename = getattr(file_obj, "name", "file") or "file"
        # Sanitize filename — keep only alphanumeric, dot, dash, underscore
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        unique_prefix = uuid.uuid4().hex[:10]
        if filename_prefix:
            safe_prefix = "".join(c if c.isalnum() or c in "_-" else "_" for c in filename_prefix)
            unique_name = f"{unique_prefix}_{safe_prefix}_{safe_name}"
        else:
            unique_name = f"{unique_prefix}_{safe_name}"

        base_dir = self.upload_dir
        if subdir:
            base_dir = f"{base_dir}/{subdir.strip('/')}"
        repo_path = f"{base_dir}/{unique_name}"

        # Read content
        try:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
        except Exception:
            pass
        content = file_obj.read() if hasattr(file_obj, "read") else bytes(file_obj)
        if not content:
            return None

        self._commit_file(repo_path, content, f"[DarkForge Art] Upload {unique_name}")

        stored_path = f"github://{self.repo_name}/{self.branch}/{repo_path}"
        public_url = self.get_public_url(repo_path)
        return GitHubUploadResult(
            repo_path=repo_path,
            stored_path=stored_path,
            public_url=public_url,
        )

    def download_file(self, stored_path: str) -> bytes:
        """
        Download a file from GitHub using the stored_path.
        Returns raw binary bytes. Supports large files (>1MB).
        """
        repo_path = self.repo_path_from_stored(stored_path)
        if not repo_path:
            raise RuntimeError(f"Invalid stored_path: {stored_path}")

        from urllib.parse import quote
        raw_url = f"https://raw.githubusercontent.com/{self.repo_name}/{self.branch}/{quote(repo_path, safe='/')}"
        resp = self.session.get(raw_url, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 0:
            return resp.content

        # Fallback: GitHub Contents API with raw media header
        headers = dict(self.session.headers)
        headers["Accept"] = "application/vnd.github.v3.raw"
        resp = self.session.get(
            f"{self.base_url}/repos/{self.repo_name}/contents/{quote(repo_path, safe='/')}",
            params={"ref": self.branch},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200 and len(resp.content) > 0:
            return resp.content

        raise RuntimeError(f"GitHub download failed for {repo_path}: status {resp.status_code}")

    def delete_file(self, stored_path: str) -> bool:
        """Delete a file from GitHub by its stored_path."""
        repo_path = self.repo_path_from_stored(stored_path)
        if not repo_path:
            return False
        sha = self._get_file_sha(repo_path)
        if not sha:
            return False

        payload = {
            "message": f"[DarkForge Art] Delete {repo_path}",
            "sha": sha,
            "branch": self.branch,
        }
        resp = self.session.delete(
            f"{self.base_url}/repos/{self.repo_name}/contents/{repo_path}",
            json=payload,
            timeout=30,
        )
        return resp.status_code < 300

    def get_public_url(self, repo_path: str) -> str:
        """Return the raw.githubusercontent.com URL for a repo path."""
        owner, repo = self.repo_name.split("/", 1) if "/" in self.repo_name else ("", self.repo_name)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{self.branch}/{repo_path}"

    @staticmethod
    def repo_path_from_stored(stored_path: str) -> Optional[str]:
        """Extract the repo-relative path from a stored_path string."""
        if not stored_path or not stored_path.startswith("github://"):
            return None
        rest = stored_path[len("github://"):]
        # github://owner/repo/branch/path/to/file
        parts = rest.split("/", 3)
        if len(parts) < 4:
            return None
        return parts[3]

    @staticmethod
    def public_url_from_stored(stored_path: str, branch: str = "main") -> Optional[str]:
        """Convert a stored_path to a browser-accessible CDN URL."""
        if not stored_path:
            return None
        if stored_path.startswith("http"):
            return stored_path
        if stored_path.startswith("/cdn/"):
            return stored_path
        if stored_path.startswith("github://"):
            rest = stored_path[len("github://"):]
            parts = rest.split("/", 3)
            if len(parts) < 4:
                return None
            owner, repo, ref, repo_path = parts
            return f"/cdn/assets/{repo_path.lstrip('/')}"
        return None


# ─── Module-level convenience functions ───────────────────────────────────────

def get_github_service() -> GitHubStorageService:
    """Return a configured GitHubStorageService from Django settings."""
    from django.conf import settings
    return GitHubStorageService(
        token=settings.GITHUB_TOKEN,
        repo_name=settings.GITHUB_REPO,
        branch=settings.GITHUB_BRANCH,
        upload_dir=settings.GITHUB_UPLOAD_DIR,
    )


def github_public_url(stored_path: str | None) -> str | None:
    """
    Convert a stored_path to a publicly accessible raw GitHub URL.
    Returns None if stored_path is empty or invalid.
    """
    if not stored_path:
        return None
    return GitHubStorageService.public_url_from_stored(
        stored_path,
        branch=getattr(settings, "GITHUB_BRANCH", "main"),
    )
