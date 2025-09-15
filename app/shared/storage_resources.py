from __future__ import annotations

import hashlib
import os
import re
import shutil
import unicodedata
from typing import Optional

from flask import current_app

_RESOURCE_DIR_NAME = "resources"


def _site_root() -> str:
    """Resolve the site root (default `/srv`)."""
    try:
        site_root = current_app.config.get("SITE_ROOT", "/srv")
    except RuntimeError:
        site_root = "/srv"
    return site_root or "/srv"


def resources_root() -> str:
    """Return the absolute path to the resources root directory."""
    return os.path.join(_site_root(), _RESOURCE_DIR_NAME)


def resource_fs_dir(resource_id: int) -> str:
    """Return the filesystem directory for a resource's stored files."""
    return os.path.join(resources_root(), str(resource_id))


def resource_fs_path(resource_id: int, filename: str) -> str:
    """Return the absolute filesystem path for a specific resource file."""
    safe_name = filename.strip("/\\")
    return os.path.join(resource_fs_dir(resource_id), safe_name)


def resource_web_url(resource_id: int, filename: str) -> str:
    """Return the public URL for the stored resource file."""
    safe_name = filename.strip("/\\")
    return f"/{_RESOURCE_DIR_NAME}/{resource_id}/{safe_name}"


def sanitize_filename(name: str) -> str:
    """Normalize an uploaded filename to a safe ASCII form."""
    raw_name = os.path.basename(name or "")
    if not raw_name:
        raw_name = "resource"

    normalized = unicodedata.normalize("NFKD", raw_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii") or raw_name

    base, ext = os.path.splitext(ascii_name)
    ext = re.sub(r"[^A-Za-z0-9]", "", ext).lower()
    if ext:
        ext = f".{ext}"

    base = base.replace(".", "-")
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-_")
    if not base:
        base = "resource"
    base = base[:64]

    digest = hashlib.sha1((ascii_name or raw_name).encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}{ext}"


def resource_path_from_value(resource_id: int, stored_value: Optional[str]) -> Optional[str]:
    """Derive the filesystem path from a stored resource value."""
    if not stored_value:
        return None

    value = stored_value.strip()
    if not value:
        return None

    prefix = f"/{_RESOURCE_DIR_NAME}/"
    if value.startswith(prefix):
        rel = value[len(prefix) :]
        parts = rel.split("/", 1)
        if len(parts) == 2:
            rid, filename = parts
            if rid == str(resource_id):
                return resource_fs_path(resource_id, filename)
            return os.path.join(resources_root(), rel)
        return os.path.join(resources_root(), rel)

    if value.startswith("/"):
        return os.path.join(_site_root(), value.lstrip("/"))

    if value.startswith(("http://", "https://")):
        return None

    if "/" in value or "\\" in value:
        return os.path.join(resources_root(), value.strip("/\\"))

    return os.path.join(resources_root(), value)


def remove_resource_file(resource_id: int, stored_value: Optional[str]) -> None:
    """Delete a stored resource file if it exists."""
    path = resource_path_from_value(resource_id, stored_value)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def remove_resource_dir(resource_id: int) -> None:
    """Delete the resource directory for an id (ignore if missing)."""
    dir_path = resource_fs_dir(resource_id)
    if os.path.isdir(dir_path):
        shutil.rmtree(dir_path, ignore_errors=True)
