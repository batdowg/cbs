from __future__ import annotations

from copy import deepcopy
from typing import Iterable

PDF_FONT_CHOICES: list[tuple[str, str]] = [
    ("Helvetica", "Helvetica"),
    ("Helvetica-Bold", "Helvetica Bold"),
    ("Helvetica-Oblique", "Helvetica Oblique"),
    ("Helvetica-BoldOblique", "Helvetica Bold Oblique"),
    ("Times-Roman", "Times Roman"),
    ("Times-Bold", "Times Bold"),
    ("Times-Italic", "Times Italic"),
    ("Times-BoldItalic", "Times Bold Italic"),
    ("Courier", "Courier"),
    ("Courier-Bold", "Courier Bold"),
    ("Courier-Oblique", "Courier Oblique"),
    ("Courier-BoldOblique", "Courier Bold Oblique"),
]

PDF_FONT_CODES: set[str] = {code for code, _ in PDF_FONT_CHOICES}

DEFAULT_LANGUAGE_FONT_CODES: list[str] = [
    "Times-Italic",
    "Times-Roman",
    "Times-Bold",
    "Helvetica",
    "Helvetica-Bold",
    "Helvetica-Oblique",
]

SAFE_FALLBACK_FONT = "Helvetica"

DETAIL_VARIABLES: list[str] = [
    "facilitators",
    "location_title",
    "dates",
    "class_days",
    "contact_hours",
    "certification_number",
]

DETAIL_LABELS: dict[str, str] = {
    "contact_hours": "Contact hours",
    "facilitators": "Facilitator(s)",
    "dates": "Dates",
    "location_title": "Location",
    "class_days": "Class days",
    "certification_number": "Certification #",
}

DETAIL_SIDES = ("LEFT", "RIGHT")

DETAIL_SIZE_MIN_PERCENT = 50
DETAIL_SIZE_MAX_PERCENT = 100

PAGE_HEIGHT_MM = {
    "A4": 297.0,
    "LETTER": 279.4,
}

_DEFAULT_DETAILS = {
    "enabled": False,
    "side": "LEFT",
    "variables": [],
    "size_percent": DETAIL_SIZE_MAX_PERCENT,
}

_DEFAULT_LAYOUT_BY_SIZE = {
    "A4": {
        "name": {"font": "Times-Italic", "y_mm": 145.0},
        "workshop": {"font": "Helvetica", "y_mm": 102.0},
        "date": {"font": "Helvetica", "y_mm": 83.0},
        "details": deepcopy(_DEFAULT_DETAILS),
    },
    "LETTER": {
        "name": {"font": "Times-Italic", "y_mm": 145.0},
        "workshop": {"font": "Helvetica", "y_mm": 102.0},
        "date": {"font": "Helvetica", "y_mm": 83.0},
        "details": deepcopy(_DEFAULT_DETAILS),
    },
}


def get_font_options() -> list[tuple[str, str]]:
    return PDF_FONT_CHOICES


def filter_font_codes(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    filtered: list[str] = []
    for value in values:
        if value in PDF_FONT_CODES and value not in seen:
            filtered.append(value)
            seen.add(value)
    return filtered


def get_default_size_layout(size: str) -> dict:
    base = _DEFAULT_LAYOUT_BY_SIZE.get(size.upper(), _DEFAULT_LAYOUT_BY_SIZE["A4"])
    return deepcopy(base)


def ensure_details_config(details: dict | None) -> dict:
    config = deepcopy(_DEFAULT_DETAILS)
    if isinstance(details, dict):
        if details.get("enabled"):
            config["enabled"] = True
        side = str(details.get("side", "LEFT")).upper()
        if side in DETAIL_SIDES:
            config["side"] = side
        variables = details.get("variables") or []
        config["variables"] = filter_detail_variables(variables)
        size_percent = details.get("size_percent")
        try:
            size_val = int(size_percent)
        except (TypeError, ValueError):
            size_val = _DEFAULT_DETAILS["size_percent"]
        if size_val < DETAIL_SIZE_MIN_PERCENT or size_val > DETAIL_SIZE_MAX_PERCENT:
            size_val = max(
                DETAIL_SIZE_MIN_PERCENT,
                min(size_val, DETAIL_SIZE_MAX_PERCENT),
            )
        config["size_percent"] = size_val
    return config


def filter_detail_variables(values: Iterable[str]) -> list[str]:
    filtered: list[str] = []
    for value in values:
        if value in DETAIL_VARIABLES and value not in filtered:
            filtered.append(value)
    return filtered


def sanitize_size_layout(size: str, layout: dict | None) -> dict:
    base = get_default_size_layout(size)
    if not isinstance(layout, dict):
        return base
    for key in ("name", "workshop", "date"):
        line = layout.get(key)
        if isinstance(line, dict):
            font = line.get("font")
            if isinstance(font, str) and font in PDF_FONT_CODES:
                base[key]["font"] = font
            y_val = line.get("y_mm")
            try:
                y_float = float(y_val)
            except (TypeError, ValueError):
                y_float = None
            if y_float is not None:
                base[key]["y_mm"] = y_float
    base["details"] = ensure_details_config(layout.get("details"))
    return base


def sanitize_series_layout(layout: dict | None) -> dict:
    if not isinstance(layout, dict):
        layout = {}
    return {
        size: sanitize_size_layout(size, layout.get(size))
        for size in ("A4", "LETTER")
    }
