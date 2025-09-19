from __future__ import annotations

import os
from typing import Iterable

from ..shared.html import sanitize_html
from ..shared.languages import LANG_CODE_NAMES

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt", ".html"}


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
    description = sanitize_html(data.get("description") or "")
    audience_raw = (data.get("audience") or "").strip().lower()
    language_raw = (data.get("language") or "").strip().lower()
    audience_map = {
        "participant": "Participant",
        "facilitator": "Facilitator",
        "both": "Both",
    }
    audience = audience_map.get(audience_raw, "Participant" if not audience_raw else None)
    language = language_raw or "en"
    if language not in LANG_CODE_NAMES:
        language = None
    cleaned.update(
        name=name,
        type=rtype,
        link=link,
        file=file,
        active=active,
        workshop_type_ids=wt_ids,
        description=description,
        audience=audience or "Participant",
        language=language or "en",
    )

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
    if audience is None:
        errors.append("Invalid audience")
    if language is None:
        errors.append("Invalid language")
        cleaned["language"] = "en"
    return errors, cleaned
