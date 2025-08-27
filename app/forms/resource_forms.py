from __future__ import annotations

import os
import re
from typing import Iterable

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt", ".html"}


def slugify_filename(name: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    ext = ext.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug}{ext}"


def validate_resource_form(data: dict, files: dict, *, require_file: bool = False) -> tuple[list[str], dict]:
    """Validate resource form input.
    Returns (errors, cleaned_data).
    """
    errors: list[str] = []
    cleaned: dict = {}
    name = (data.get("name") or "").strip()
    rtype = (data.get("type") or "").upper()
    link = (data.get("link") or "").strip()
    file = files.get("file")
    active = bool(data.get("active"))
    wt_ids = [int(x) for x in data.getlist("workshop_types") if x.isdigit()]
    cleaned.update(name=name, type=rtype, link=link, file=file, active=active, workshop_type_ids=wt_ids)

    if not name:
        errors.append("Name required")
    if rtype not in {"LINK", "DOCUMENT", "APP"}:
        errors.append("Invalid type")
    elif rtype in {"LINK", "APP"}:
        if not link.startswith("http://") and not link.startswith("https://"):
            errors.append("Valid URL required")
        if file and getattr(file, "filename", ""):
            errors.append("File not allowed for this type")
    elif rtype == "DOCUMENT":
        if require_file and (not file or not getattr(file, "filename", "")):
            errors.append("File required")
        if file and getattr(file, "filename", ""):
            _, ext = os.path.splitext(file.filename)
            if ext.lower() not in ALLOWED_EXTENSIONS:
                errors.append("Invalid file type")
    return errors, cleaned
