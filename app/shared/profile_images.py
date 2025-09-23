from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from typing import Optional

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 4096
PROFILE_ROOT = "uploads/profile_pics"


@dataclass
class ProfileImageResult:
    relative_path: str


class ProfileImageError(ValueError):
    pass


def _sanitize_filename(filename: str) -> str:
    cleaned = secure_filename(filename or "")
    if not cleaned:
        raise ProfileImageError("Invalid file name.")
    return cleaned


def _validate_extension(filename: str) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ProfileImageError("Only PNG and JPG images are allowed.")


def _ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _validate_image_bytes(raw: bytes) -> tuple[int, int]:
    if len(raw) > MAX_BYTES:
        raise ProfileImageError("Image is larger than 2 MB.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except (UnidentifiedImageError, OSError):  # pragma: no cover - pillow detail
        raise ProfileImageError("Upload must be a valid image.")
    width, height = image.size
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ProfileImageError("Image dimensions are too large.")
    return width, height


def save_profile_image(
    upload: FileStorage, owner_key: str, previous_path: Optional[str] = None
) -> ProfileImageResult:
    filename = _sanitize_filename(upload.filename or "")
    _validate_extension(filename)

    data = upload.read()
    upload.stream.seek(0)
    _validate_image_bytes(data)

    site_root = current_app.config.get("SITE_ROOT", "/srv")
    owner_segment = re.sub(r"[^A-Za-z0-9_-]", "", owner_key)
    if not owner_segment:
        raise ProfileImageError("Invalid owner identifier.")
    directory = os.path.join(site_root, PROFILE_ROOT, owner_segment)
    _ensure_directory(directory)

    target_path = os.path.join(directory, filename)
    with open(target_path, "wb") as fh:
        fh.write(data)

    if previous_path:
        _cleanup_previous(previous_path, target_path)

    relative = os.path.relpath(target_path, site_root)
    return ProfileImageResult(relative_path="/" + relative.replace(os.sep, "/"))


def _cleanup_previous(previous_path: str, current_path: str) -> None:
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    normalized = previous_path.lstrip("/")
    candidate = os.path.join(site_root, normalized)
    try:
        if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(current_path):
            os.remove(candidate)
    except OSError:
        pass


def resolve_profile_image(relative_path: Optional[str]) -> Optional[str]:
    if not relative_path:
        return None
    safe = relative_path.strip()
    if not safe.startswith("/"):
        safe = "/" + safe
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    candidate = os.path.join(site_root, safe.lstrip("/"))
    if not os.path.isfile(candidate):
        return None
    return safe


def delete_profile_image(relative_path: Optional[str]) -> None:
    if not relative_path:
        return
    site_root = current_app.config.get("SITE_ROOT", "/srv")
    normalized = relative_path.lstrip("/")
    candidate = os.path.join(site_root, normalized)
    try:
        if os.path.isfile(candidate):
            os.remove(candidate)
    except OSError:
        pass
