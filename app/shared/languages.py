from __future__ import annotations

from typing import List, Tuple

from ..models import Language

# Mapping of language codes to human-readable names
LANG_CODE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "ja": "Japanese",
    "de": "German",
    "nl": "Dutch",
    "zh": "Chinese",
}

NAME_TO_CODE = {v: k for k, v in LANG_CODE_NAMES.items()}


def get_language_options() -> List[Tuple[str, str]]:
    """Return active language code/name pairs sorted by Language.sort_order."""
    langs = (
        Language.query.filter_by(is_active=True)
        .order_by(Language.sort_order, Language.name)
        .all()
    )
    opts: List[Tuple[str, str]] = []
    for lang in langs:
        code = NAME_TO_CODE.get(lang.name)
        if code:
            opts.append((code, lang.name))
    return opts


def code_to_label(code: str) -> str:
    """Return human-readable language name for a code."""
    return LANG_CODE_NAMES.get(code, code)
